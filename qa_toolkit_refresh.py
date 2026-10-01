#!/usr/bin/env python3
"""Check whether your installed initqa prompt is current, and refresh it.

Pure standard library. Python 3.8+. No install.

WHY THIS EXISTS
The initqa prompt is installed as a file, so it drifts. The repository gains
fixes; the copy on disk keeps the old ones. A stale bootstrap prompt is worse
than no prompt, because it still reads as authoritative - it will happily
scaffold a flow using guidance that was already found to be wrong.

But refreshing unconditionally is worse still. It makes the bootstrap depend
on the network on every single run, and a bootstrap that fails because a
laptop is on a train is a bootstrap nobody runs. So the check is tri-state and
advisory:

    CURRENT    network reachable, remote version == local  -> print nothing
    STALE      network reachable, versions differ         -> offer the update
    OFFLINE    network unreachable                         -> print nothing
    AMBIGUOUS  server answered but could not be trusted    -> treat as STALE

OFFLINE is not an error. It is the expected state on a train, behind a proxy,
or in an air-gapped environment, and the caller must proceed exactly as it
would have. Nothing here ever blocks the bootstrap.

THE ASYMMETRY IS DELIBERATE
An untrustworthy answer is reported as STALE, never as CURRENT. A redundant
"an update is available" note costs the user one line. Silently believing you
are current is precisely the failure this toolkit exists to prevent, so the
error is always assumed to point at the pessimistic side.

WHY THE GITHUB API AND NOT A RAW FILE URL
Measured on this repository: after a push, the `raw.githubusercontent.com`/main
URL kept serving the PREVIOUS file for an extended period, and a `?cb=<ts>`
cache-buster did not defeat it. A raw fetch would therefore report CURRENT
against stale content. The contents API reflects the current ref, so version
comparison is done there. The stale-response trap is recorded in README.md.

SAFETY
--apply refuses to overwrite an existing prompt with anything that does not
look like a prompt: it must have a `---` frontmatter block and a recognised
version marker. A truncated download cannot replace a working file.

USAGE
  python qa_toolkit_refresh.py                     # silent unless stale
  python qa_toolkit_refresh.py --json              # machine-readable
  python qa_toolkit_refresh.py --apply             # download and install
  python qa_toolkit_refresh.py --dest ./initqa.prompt.md --apply
  python qa_toolkit_refresh.py --strict            # exit 1 unless CURRENT

EXIT CODES
  0  always, unless --strict and the state is not CURRENT
  Never exits non-zero on a network problem, so it is safe in a pipeline.
"""
import argparse
import base64
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REPO = "felipeUmbra/qa-toolkit"
DEFAULT_REF = "main"
PROMPT_NAME = "initqa.prompt.md"
DEFAULT_TIMEOUT = 5.0

CURRENT, STALE, OFFLINE, AMBIGUOUS, MISSING, ERROR = (
    "current", "stale", "offline", "ambiguous", "missing", "error",
)

# The marker build_prompt.py injects into the prompt it generates.
MARKER_RE = re.compile(r"<!--\s*toolkit-version:\s*([^\s]+?)\s*-->")


class Unreachable(Exception):
    """The network could not be reached. Expected, not exceptional."""


class Untrusted(Exception):
    """A server answered, but the answer cannot be relied upon."""


def github_headers(token=None):
    headers = {
        "User-Agent": "qa-toolkit-refresh",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = "Bearer %s" % token
    return headers


def _classify(exc):
    """Decide whether an exception means offline or merely untrustworthy.

    The distinction matters: offline is silent and expected, whereas a server
    that answered and gave something unusable should still nudge the user.
    """
    if isinstance(exc, urllib.error.HTTPError):
        # A status code means something answered. 404 is a wrong ref, 403 and
        # 429 are rate limits, 5xx is a broken server - all untrustworthy,
        # none of them "no network".
        return AMBIGUOUS
    if isinstance(exc, (urllib.error.URLError, socket.timeout, TimeoutError)):
        return OFFLINE
    if isinstance(exc, OSError):
        return OFFLINE
    return AMBIGUOUS


def default_fetch(url, token=None, timeout=DEFAULT_TIMEOUT):
    req = urllib.request.Request(url, headers=github_headers(token))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


class Client(object):
    """Talks to the toolkit repository. Injectable for tests."""

    def __init__(self, repo=DEFAULT_REPO, ref=DEFAULT_REF, token=None,
                 timeout=DEFAULT_TIMEOUT, fetch=None):
        self.repo = repo
        self.ref = ref
        self.token = token
        self.timeout = timeout
        self.fetch = fetch or default_fetch

    def _get(self, url):
        try:
            return self.fetch(url, self.token, self.timeout)
        except Exception as exc:  # noqa: BLE001 - deliberately broad
            state = _classify(exc)
            if state == OFFLINE:
                raise Unreachable(str(exc))
            raise Untrusted(str(exc))

    def _contents(self, path):
        url = ("https://api.github.com/repos/%s/contents/%s?ref=%s"
               % (self.repo, path, self.ref))
        raw = self._get(url)
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise Untrusted("contents response was not JSON: %s" % exc)
        if not isinstance(payload, dict) or "content" not in payload:
            raise Untrusted("contents response had no content field")
        blob = payload.get("content") or ""
        try:
            # GitHub wraps base64 at 60 columns, so whitespace must go.
            return base64.b64decode(blob.replace("\n", "")).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise Untrusted("contents were not valid base64 text: %s" % exc)

    def remote_version(self):
        return read_version(self._contents("VERSION"))

    def remote_prompt(self):
        return self._contents(PROMPT_NAME)


def read_version(text):
    """Pull a version token out of toolkit text.

    Accepts either a bare token (the VERSION file, e.g. "v3") or the HTML
    comment marker embedded in a prompt. Handling both is deliberate: the
    remote VERSION file holds only the bare token, while a local install has
    the marker, so reading only one form made every remote lookup fail.
    """
    match = MARKER_RE.search(text or "")
    if match:
        return match.group(1)
    stripped = (text or "").strip()
    if stripped and re.fullmatch(r"v?\d+(?:\.\d+)*(?:[-+][\w.]+)?", stripped):
        return stripped
    return ""


def looks_like_prompt(text):
    """Refuse to install anything that is not recognisably the prompt."""
    if not text or not text.lstrip().startswith("---"):
        return False
    if not re.search(r"(?m)^---\s*$", text[3:]):
        return False
    return bool(MARKER_RE.search(text))


def prompts_dir():
    """Where VS Code keeps user prompts, per platform."""
    override = os.environ.get("QA_TOOLKIT_PROMPTS_DIR")
    if override:
        return Path(override)
    home = Path.home()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / "Code" / "User" / "prompts"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Code" / "User" / "prompts"
    return home / ".config" / "Code" / "User" / "prompts"


def classify(local_version, client):
    """Decide the state. Never raises, always returns a 3-tuple.

    Returns (state, remote_version, detail). The two trailing fields are kept
    separate because both are strings and conflating them is how a caller ends
    up printing "unknown -> unknown": detail is prose for a human, whereas
    remote_version is a version to compare against.
    """
    if not local_version:
        return MISSING, "", "local prompt carries no version marker"
    try:
        remote = client.remote_version()
    except Unreachable as exc:
        return OFFLINE, "", str(exc)
    except Untrusted as exc:
        return AMBIGUOUS, "", str(exc)
    if not remote:
        return AMBIGUOUS, "", "remote VERSION file carried no marker"
    if remote == local_version:
        return CURRENT, remote, ""
    return STALE, remote, "local %s, remote %s" % (local_version, remote)


def _read_local(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return read_version(fh.read()), None
    except OSError as exc:
        return "", str(exc)
    except UnicodeDecodeError as exc:
        return "", "local prompt is not UTF-8: %s" % exc


def apply_update(client, dest, local_version):
    """Fetch and install, but only over something that is safe to replace."""
    try:
        text = client.remote_prompt()
    except Unreachable:
        return False, "could not reach the network"
    except Untrusted as exc:
        return False, "download not trustworthy: %s" % exc

    if not looks_like_prompt(text):
        return False, "downloaded file was not a recognisable prompt; left local copy alone"

    new_version = read_version(text)
    if local_version and new_version == local_version:
        return False, "downloaded copy is the same version as the local one"

    dest = Path(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".new")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        os.replace(str(tmp), str(dest))
    except OSError as exc:
        return False, "could not write %s: %s" % (dest, exc)

    return True, "installed %s version %s" % (new_version, dest)


def main(argv=None, client=None, fetch=None):
    parser = argparse.ArgumentParser(
        description="Check whether the installed initqa prompt is current.")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument("--dest", default=None,
                        help="path to the installed prompt (default: auto-detect)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--apply", action="store_true",
                        help="download and install when stale")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    if client is None:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        client = Client(repo=args.repo, ref=args.ref, token=token,
                        timeout=args.timeout, fetch=fetch)

    dest = Path(args.dest) if args.dest else prompts_dir() / PROMPT_NAME

    result = {"state": ERROR, "local_version": "", "remote_version": "",
              "dest": str(dest), "detail": "", "updated": False}

    try:
        local_version, read_err = _read_local(dest)
        result["local_version"] = local_version
        if read_err:
            result["state"] = MISSING
            result["detail"] = read_err
        else:
            state, remote, detail = classify(local_version, client)
            result["state"] = state
            result["remote_version"] = remote
            result["detail"] = detail

        needs_update = result["state"] in (STALE, AMBIGUOUS, MISSING)
        if args.apply and needs_update:
            ok, message = apply_update(client, dest, local_version)
            result["updated"] = ok
            result["detail"] = message

        if args.as_json:
            print(json.dumps(result, indent=2, sort_keys=True))
        elif result["state"] == MISSING and result["updated"]:
            print(result["detail"])
        elif result["state"] == MISSING:
            print("initqa prompt not installed at %s" % dest)
            print("Run with --apply to install it, or copy initqa.prompt.md "
                  "there yourself.")
        elif needs_update:
            print("initqa toolkit %s -> %s available."
                  % (result["local_version"] or "unknown",
                     result["remote_version"] or "unknown"))
            if result["updated"]:
                print(result["detail"])
            else:
                print("Run with --apply to install it, or continue as-is.")
        elif args.apply:
            print("initqa prompt is current (%s)." % result["local_version"])
        # CURRENT and OFFLINE are silent by design.

        if args.strict and result["state"] != CURRENT:
            return 1
        return 0
    except Exception as exc:  # noqa: BLE001 - a diagnostic must never crash
        result["state"] = ERROR
        result["detail"] = str(exc)
        if args.as_json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("refresh check could not complete: %s" % exc, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())