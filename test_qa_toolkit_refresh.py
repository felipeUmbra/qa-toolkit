"""Tests for qa_toolkit_refresh.py.

The behaviour that matters most is the one nobody will ever see working: the
offline path. If a refresh check blocks, errors, or prompts when there is no
network, the bootstrap it guards becomes unrunnable on a train. So the offline
cases are tested first and treated as the load-bearing requirement.

Pure standard library, so these run on a machine with nothing installed.
"""
import io
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qa_toolkit_refresh as refresh


def fake_fetch(payloads):
    """Build a fetch callable serving canned API responses by URL fragment."""
    calls = []

    def _fetch(url, token=None, timeout=None):
        calls.append(url)
        for fragment, body in payloads.items():
            if fragment in url:
                if isinstance(body, Exception):
                    raise body
                return body
        raise urllib.error.URLError("no route to host")

    _fetch.calls = calls
    return _fetch


def api_contents(text):
    import base64
    blob = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return json.dumps({"content": blob})


def marker(version):
    """The HTML comment form embedded in a built prompt."""
    return "<!-- toolkit-version: %s -->" % version


def version_file(version):
    """The bare-token form the remote VERSION file actually contains.

    This distinction is load-bearing. The first version of these tests used
    marker() for the remote VERSION payload, so every case passed while the
    real helper failed against the real API - it looked for a comment in a
    file that holds nothing but "v3". Fake data must match production shape or
    it proves nothing.
    """
    return version


CURRENT_PROMPT = "---\ndescription: x\n---\n\n# hi\n" + marker("v9")


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmp, "initqa.prompt.md")
        with open(self.dest, "w", encoding="utf-8") as fh:
            fh.write(CURRENT_PROMPT)

    def _client(self, version="v9", prompt=None, raise_exc=None):
        payloads = {}
        if raise_exc is not None:
            payloads["/contents/VERSION"] = raise_exc
        else:
            payloads["/contents/VERSION"] = api_contents(version_file(version))
        if prompt is not None:
            payloads["/contents/initqa.prompt.md"] = prompt
        fetch = fake_fetch(payloads)
        return refresh.Client(fetch=fetch), fetch

    def test_up_to_date_is_silent_and_current(self):
        client, _ = self._client(version="v9")
        state, remote, detail = refresh.classify("v9", client)
        self.assertEqual(state, refresh.CURRENT)
        self.assertEqual(remote, "v9")
        self.assertEqual(detail, "")

    def test_up_to_date_prints_nothing_at_the_cli(self):
        client, _ = self._client(version="v9")
        buf = io.StringIO()
        with redirect_stdout(buf):
            state, _r, _d = refresh.classify("v9", client)
        self.assertEqual(state, refresh.CURRENT)
        self.assertEqual(buf.getvalue(), "")

    def test_offline_returns_offline_and_never_raises(self):
        client, _ = self._client(raise_exc=urllib.error.URLError("no route"))
        state, remote, _detail = refresh.classify("v9", client)
        self.assertEqual(state, refresh.OFFLINE)
        self.assertEqual(remote, "", "offline must not report a remote version")

    def test_timeout_is_offline_not_a_crash(self):
        client, _ = self._client(raise_exc=socket.timeout("timed out"))
        state, _r, _d = refresh.classify("v9", client)
        self.assertEqual(state, refresh.OFFLINE)

    def test_http_error_is_ambiguous_so_we_still_nudge(self):
        client, _ = self._client(raise_exc=urllib.error.HTTPError("u", 500, "boom", None, None))
        state, _r, _d = refresh.classify("v9", client)
        self.assertEqual(state, refresh.AMBIGUOUS)

    def test_stale_when_remote_newer(self):
        client, _ = self._client(version="v10")
        state, remote, _detail = refresh.classify("v9", client)
        self.assertEqual(state, refresh.STALE)
        self.assertEqual(remote, "v10")

    def test_missing_version_marker_reports_missing(self):
        client, _ = self._client()
        state, _r, detail = refresh.classify("", client)
        self.assertEqual(state, refresh.MISSING)
        self.assertIn("no version marker", detail)

    def test_non_json_remote_is_untrusted(self):
        client, _ = self._client(raise_exc="this is not json")
        state, _r, _d = refresh.classify("v9", client)
        self.assertEqual(state, refresh.AMBIGUOUS)

    def test_reads_a_bare_token_as_well_as_a_marker(self):
        """Regression: the remote VERSION file holds only a bare token.

        The original implementation searched for the HTML comment marker in
        both places, so against the real API it found nothing and reported
        'ambiguous' forever - while every test passed, because the fakes
        used marker-formatted payloads the real repo never sends.
        """
        self.assertEqual(refresh.read_version("v12"), "v12")
        self.assertEqual(refresh.read_version("  v12\n"), "v12")
        self.assertEqual(refresh.read_version(marker("v12")), "v12")
        self.assertEqual(refresh.read_version("not a version"), "")
        self.assertEqual(refresh.read_version(""), "")

    def test_remote_version_reads_a_real_bare_token(self):
        client, _ = self._client(version="v42")
        self.assertEqual(client.remote_version(), "v42")


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = Path(self.tmp) / "initqa.prompt.md"
        self.dest.write_text(CURRENT_PROMPT, encoding="utf-8")

    def _client(self, prompt):
        return refresh.Client(fetch=fake_fetch({
            "/contents/initqa.prompt.md": api_contents(prompt),
        }))

    def test_apply_installs_newer_version(self):
        new = CURRENT_PROMPT.replace("v9", "v10")
        ok, msg = refresh.apply_update(self._client(new), self.dest, "v9")
        self.assertTrue(ok)
        self.assertIn("v10", msg)
        self.assertIn("v10", self.dest.read_text(encoding="utf-8"))

    def test_refuses_to_install_a_non_prompt(self):
        """A truncated or error-page download must not replace a good file."""
        ok, msg = refresh.apply_update(self._client("<html>404</html>"), self.dest, "v9")
        self.assertFalse(ok)
        self.assertIn("not a recognisable prompt", msg)
        self.assertIn("v9", self.dest.read_text(encoding="utf-8"))

    def test_no_op_when_downloaded_version_matches(self):
        ok, msg = refresh.apply_update(self._client(CURRENT_PROMPT), self.dest, "v9")
        self.assertFalse(ok)
        self.assertIn("same version", msg)

    def test_offline_apply_leaves_file_untouched(self):
        client = refresh.Client(fetch=fake_fetch({}))
        ok, msg = refresh.apply_update(client, self.dest, "v9")
        self.assertFalse(ok)
        self.assertIn("network", msg)
        self.assertIn("v9", self.dest.read_text(encoding="utf-8"))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmp, "initqa.prompt.md")
        with open(self.dest, "w", encoding="utf-8") as fh:
            fh.write(CURRENT_PROMPT)

    def _run(self, argv, fetch):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = refresh.main(argv, fetch=fetch)
        return code, buf.getvalue()

    def test_offline_run_prints_nothing_and_exits_zero(self):
        """The headline requirement: no network means silence and success."""
        fetch = fake_fetch({})
        code, out = self._run(["--dest", self.dest], fetch)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_offline_state_is_reported_as_offline_in_json(self):
        fetch = fake_fetch({})
        _code, out = self._run(["--dest", self.dest, "--json"], fetch)
        payload = json.loads(out)
        self.assertEqual(payload["state"], refresh.OFFLINE)
        self.assertEqual(payload["updated"], False)

    def test_stale_run_offers_the_update(self):
        fetch = fake_fetch({"/contents/VERSION": api_contents(version_file("v10"))})
        code, out = self._run(["--dest", self.dest], fetch)
        self.assertEqual(code, 0)
        self.assertIn("v9 -> v10", out)
        self.assertIn("--apply", out)

    def test_current_run_is_silent(self):
        fetch = fake_fetch({"/contents/VERSION": api_contents(version_file("v9"))})
        code, out = self._run(["--dest", self.dest], fetch)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_strict_fails_when_offline_but_plain_run_does_not(self):
        fetch = fake_fetch({})
        code_ok, _ = self._run(["--dest", self.dest], fetch)
        self.assertEqual(code_ok, 0)
        code_strict, _ = self._run(["--dest", self.dest, "--strict"], fetch)
        self.assertEqual(code_strict, 1)

    def test_json_reports_state_offline(self):
        fetch = fake_fetch({})
        code, out = self._run(["--dest", self.dest, "--json"], fetch)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["state"], refresh.OFFLINE)

    def test_missing_file_is_reported_not_crashed(self):
        missing = os.path.join(self.tmp, "nope", "initqa.prompt.md")
        code, out = self._run(["--dest", missing], fake_fetch({}))
        self.assertEqual(code, 0)
        self.assertIn("not found", out)

    def test_offline_never_nets_out_of_scope_urls(self):
        """It must only ever ask the API about VERSION and the prompt."""
        fetch = fake_fetch({"/contents/VERSION": api_contents(version_file("v9"))})
        self._run(["--dest", self.dest], fetch)
        for url in fetch.calls:
            self.assertTrue(
                url.startswith("https://api.github.com/repos/"),
                "unexpected host: %s" % url,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)