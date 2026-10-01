---
description: "Set up this project's quality flow from scratch - interview the user, then scaffold tests, accessibility gates, CI, a project QA agent, and a defect register in the right order."
argument-hint: "[optional: path to audit, defaults to the workspace]"
agent: "agent"
tools: ["codebase", "search", "usages", "problems", "editFiles", "createFile", "runCommands", "runTasks", "runTests", "testFailure", "terminalLastCommand", "terminalSelection", "getTaskOutput", "killTerminal", "notebooks", "githubRepo", "github_text_search", "fetch", "vscode/askQuestions"]
---

# Initialise this project's quality flow
<!-- toolkit-version: v1 -->
Your job is to stand up a working quality flow for THIS repository, in the
right order, and to prove each piece actually gates. Work through the phases
below in order. Do not skip phase 1 - asking is not optional.

Two pre-flight checks run before anything else: is this prompt current,
and is there an interpreter to run the audit with. Neither may block the flow.

Two rules govern everything else:

- **Never scaffold over something that already exists.** Phase 1 exists to
  prevent a second runner or a duplicated CI job.
- **A gate that has never been seen failing is not a gate.** Phase 9 exists
  because scaffolding nobody verified is decoration.

---

## Phase 0 - Pre-flight: check this prompt is current, and that a runtime exists

### 0a. Is the toolkit current?

You may be running an older copy of this prompt. The repository it came from
gains fixes; an installed file does not. A stale bootstrap prompt is worse than
none, because it still reads as authoritative - it will happily scaffold a
quality flow using guidance already found to be wrong.

Check your own version marker against the published one. Run the shipped helper:

```bash
python qa_toolkit_refresh.py            # silent unless an update exists
python qa_toolkit_refresh.py --json     # state, local and remote version
python qa_toolkit_refresh.py --apply    # download and install
```

Act on the state like this, and never block on any of it:

| State | What it means | What you do |
|---|---|---|
| `current` | You match the published version | Say nothing. Continue to phase 1. |
| `stale` | A newer version exists | Tell the user the version pair and offer to install it. **Continue regardless** - never block phase 1 on a download. |
| `offline` | No network, or unreachable | Say nothing. Continue exactly as you would have. This is expected on a train, behind a proxy, or in an air-gapped environment. |
| `ambiguous` | A server answered but the answer is unusable | Treat as `stale` and mention it in one line. An untrustworthy answer is never treated as `current`. |
| `missing` | This prompt has no version marker | Continue silently. Do not reconstruct the refresh logic from memory. |

Three rules govern this phase:

1. **Never block the bootstrap on the network.** If the check fails, times out,
   or cannot run at all, proceed. A bootstrap that fails on a train is a
   bootstrap nobody runs.
2. **Never announce a check that did not happen.** Only report a version if you
   actually compared two, and say plainly when you could not.
3. **Never reconstruct the refresh logic from memory** if the helper is
   missing. Download it, or report that it is absent.

### 0b. Is there an interpreter to run the audit with?

Phase 2 runs a Python script, and this toolkit exists to serve JavaScript
projects that have never had Python installed. So check before relying on it:

```bash
python3 --version 2>/dev/null || python --version 2>/dev/null || py --version 2>/dev/null || echo "NO_PYTHON"
```

**If this prints `NO_PYTHON`, do not silently continue to phase 2.** A missing
interpreter makes the audit fail in one of two ways, and both are dangerous:

- **`python` is not recognised.** The command errors, and an agent that does
  not check will report "the audit produced no findings" and conclude the
  project has no quality flow at all. It has one; the tool simply never ran.
- **`python` resolves to a shim** - notably the Microsoft Store alias, which can
  print nothing and **exit 0**. That reads exactly like a clean audit of an
  empty project, and it is the worst case: it is indistinguishable from success.

Either way, say so plainly and use the phase 2 fallback rather than proceeding
as though the audit ran.

If it prints a version, note it and carry on. When a version *is* available,
prefer `python3`, then `python`, then `py` - and do not install or upgrade an
interpreter without asking the user first.

### If no interpreter is available

Do not stop the bootstrap, and do not install Python uninvited. In order of
preference:

1. **Use what the project already has.** A JavaScript project has `node`. The
   audit is a read-only inspection, so porting its checks to a short `node -e`
   script is entirely mechanical: read the files, apply the same rules, print
   the same layers. Say that you did this and why.
2. **Do the audit by reading.** Phase 2 can be done with the file-reading tools
   alone - check `package.json` scripts, workflow files, test configs, and agent
   files directly. Slower, and it will miss what a glob would have caught, but
   it is real evidence rather than an assumption.
3. **Tell the user what is skipped.** If neither is possible, say plainly that
   the automated audit did not run and why. Do not report a clean result.

What must never happen: continuing as though the audit ran and found nothing.
An audit that never executed and an audit that found nothing look identical, and
the second reading is the one that gets believed.

---

## Phase 1 - Interview the user

Do not assume. Read the repository first (`package.json`, lockfiles, build and
test configs, existing workflows, any agent or instruction files), so most of
your questions are already answered and you only ask about what you genuinely
cannot infer.

Then use the **askQuestions** tool to confirm the gaps. Ask about these, and
skip any the repo already answers clearly:

1. **Unit/integration runner** - Vitest, Jest, pytest, go test, or keep what is
   there.
2. **E2E driver** - Playwright, Cypress, or none for now.
3. **Accessibility** - axe-core plus a contrast script, Lighthouse only, or
   defer.
4. **Target browsers and viewports** for E2E.
5. **Should E2E run on every PR**, or only on merge to the default branch?
6. **Is there an external API boundary** that needs contract tests or fakes?
7. **Should the defect register file issues automatically**, and with what
   impact bands?

Present each choice as a short menu of at most three options, with one marked
as your recommendation and a sentence of reasoning. Do not present a bare
menu, and do not exceed three options.

> Playwright is the usual recommendation for E2E because one config covers
> multiple viewports and, later, Firefox and WebKit. Cypress would mean a
> second runner for the cross-browser set. Say why in THIS project's terms
> though - the recommendation must follow from what you read, not from habit.

---

## Phase 2 - Audit what already exists

Write the audit script below to `scripts/qa_bootstrap_audit.py` and run it:

```bash
python scripts/qa_bootstrap_audit.py .
python scripts/qa_bootstrap_audit.py . --json      # if you want to parse it
```

It is read-only: it runs no tests, opens no network connection, and writes
nothing. It reports each quality layer as present or absent, **and whether it
is wired to anything** - an unwired gate cannot fail, however many files it
has.

The warning that matters most is `agent-never-invoked`: an agent file that
documents bug-filing rules while no workflow invokes the agent. That exact state
existed in a real repository, and it is why a defect could sit in the first
commit, survive roughly fifty commits, and be found and fixed without ever being
registered.

Reconcile the audit against phase 1 before writing anything. Where they
disagree, say so and trust the audit for what is present.

**If phase 0b found no interpreter, do not run the script below.** Follow the
fallback in phase 0 instead - port the checks to `node`, or audit by reading.
Either way the audit layer is still written to `scripts/qa_bootstrap_audit.py`
so the project keeps it; you are only choosing how to produce this one run's
findings.

### The audit script

Save this verbatim as `scripts/qa_bootstrap_audit.py`. It is pure standard
library - Python 3.8+, no install, no dependencies.

```python
"""Audit a repository's quality flow before bootstrapping anything.

WHY THIS EXISTS
Bootstrapping a repo that already has half a flow is a common and expensive
mistake: you end up with two runners, two selector layers, or a duplicated CI
job, and the repo now has two sources of truth. The fix is to look before
scaffolding.

This is READ-ONLY. It runs no tests, hits no network, and writes nothing.

THE FINDING THAT MATTERS MOST
Gates catch regressions in behaviour that is already asserted. They cannot
report a defect nobody wrote a test about. The failure this catches is an agent
file that documents bug-filing rules while NO workflow ever invokes the agent -
an uninvoked rule is a comment that reads like a guarantee, and the defect
register stays empty. That exact state existed in a real repo: the rules were
written, the labels existed, and a defect that sat in the first commit was
found and fixed without ever being registered.

Stderr is used for failures and stdout for findings, so this composes:
    python qa_bootstrap_audit.py --json | jq .

USAGE
  python qa_bootstrap_audit.py [path]        # defaults to cwd
  python qa_bootstrap_audit.py --json
  python qa_bootstrap_audit.py --strict      # exit 1 on any warning
"""
import argparse
import json
import os
import re
import sys
from glob import glob

# Directories holding generated output, never source.
SKIP_DIRS = {
    "node_modules", "dist", "build", "coverage", ".git", "playwright-report",
    "test-results", "htmlcov", "__pycache__", "vendor", "target", ".next",
    "out", ".venv", "venv",
}

# layer key -> (display name, patterns, gate-evidence tokens)
LAYERS = [
    ("unit", "Unit / integration",
     ["vitest.config.*", "jest.config.*", "vitest.workspace.*", "karma.conf.*",
      "**/*.test.js", "**/*.test.ts", "**/*.test.tsx", "**/*.spec.js",
      "**/*.spec.ts", "**/*.test.py", "**/*_test.py", "pytest.ini", "tox.ini",
      "conftest.py", "pyproject.toml"],
     ["coverage", "threshold", "test:unit", "pytest", "go test", "npm test"]),

    ("e2e", "E2E",
     ["playwright.config.*", "cypress.config.*", "cypress.json", "wdio.conf.*",
      "tests/e2e/**", "test/e2e/**", "e2e/**", "playwright/**", "cypress/**",
      "**/*.e2e.{ts,js}", "**/e2e/*_spec.rb"],
     ["test:e2e", "playwright", "cypress"]),

    ("a11y", "Accessibility scanning",
     ["**/axe*.{js,ts,mjs,cjs}", "**/*a11y*.{js,ts,mjs,cjs}",
      "**/*contrast*.{js,ts,mjs,cjs,py}", ".pa11y*",
      "**/lighthou*.{js,json,yml,yaml}", "**/beacon*.{js,yml,yaml}"],
     ["a11y", "contrast", "axe", "lighthouse", "pa11y"]),

    ("perf", "Performance budget",
     ["lighthouerc.*", "**/lighthouse-ci.*", "**/sitespeed*",
      "**/*bundlesize*", "**/*performance-budget*"],
     ["lighthouse", "budget", "bundlesize"]),

    ("ci", "CI workflows",
     [".github/workflows/*.yml", ".github/workflows/*.yaml",
      ".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile",
      ".circleci/config.yml", ".buildkite/*.yml"],
     None),

    ("deps", "Dependency automation",
     [".github/dependabot.yml", ".github/dependabot.yaml",
      ".github/renovate.json", "renovate.json", ".pre-commit-config.yaml"],
     ["dependabot", "renovate"]),

    ("container", "Container / infra",
     ["Dockerfile*", "docker-compose*.y*ml", "compose.y*ml",
      "k8s/**", "kubernetes/**", "*.tf", "serverless.y*ml"],
     ["docker", "compose", "kubectl", "terraform"]),

    ("agent", "Project agent file",
     [".github/agents/*.md", ".claude/agents/*.md", ".cursor/agents/*.md",
      "AGENTS.md", "CLAUDE.md", ".cursorrules", ".windsurfrules",
      ".github/copilot-instructions.md", ".github/copilot-instructions.md"],
     None),
]

# Files that must exist for gates to be meaningful, mapped to the layer they
# prove. A test file alone does not gate anything.
GATE_PROOF = {
    "ci": [".github/workflows", ".gitlab-ci.yml", "azure-pipelines.yml",
           "Jenkinsfile", ".circleci"],
}

STACK_MARKERS = [
    ("TypeScript", "typescript"), ("React", "react"), ("Vue", "vue"),
    ("Svelte", "svelte"), ("Angular", "@angular/core"), ("Next.js", "next"),
    ("Nuxt", "nuxt"), ("SvelteKit", "sveltekit"), ("Remix", "@remix-run"),
    ("Astro", "astro"), ("Vite", "vite"), ("Angular CLI", "@angular/cli"),
    ("Express", "express"), ("Fastify", "fastify"), ("NestJS", "@nestjs/core"),
    ("Django", "django"), ("Flask", "flask"), ("FastAPI", "fastapi"),
    ("Rails", "rails"), ("Laravel", "laravel"), ("Spring", "spring-boot"),
]

STACK_FILES = [
    ("Python", ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]),
    ("Go", ["go.mod"]), ("Rust", ["Cargo.toml"]), ("Ruby", ["Gemfile"]),
    ("Java", ["pom.xml", "build.gradle", "build.gradle.kts"]),
    (".NET", ["*.csproj", "*.sln"]), ("PHP", ["composer.json"]),
    ("Elixir", ["mix.exs"]),
]


def expand_braces(pattern):
    """Expand `{a,b}` alternatives.

    Python's glob does NOT support brace expansion - `**/*.{js,ts}` silently
    matches nothing. A silent zero-match is indistinguishable from "this layer
    does not exist", which is the worst possible failure for an audit: it
    reports a healthy repo as untested. Hence explicit expansion.

    Returns a DE-DUPLICATED, order-preserving list. Nested alternatives
    (`a/{b,c/{b,d}}`) legitimately expand to a repeated `a/b`, and a caller
    counting results would otherwise double-count one path.

    Also raises on an unbalanced brace rather than passing it through, because
    that would fail the same way but invisibly.
    """
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        if "{" in pattern or "}" in pattern:
            raise ValueError(f"unbalanced brace in pattern: {pattern}")
        return [pattern]
    out = []
    for alt in m.group(1).split(","):
        out.extend(expand_braces(
            pattern[:m.start()] + alt.strip() + pattern[m.end():]))
    seen, uniq = set(), []
    for o in out:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    return uniq


def find_all(root, patterns):
    """Expand globs to repo-relative paths, excluding generated output."""
    found = set()
    for pat in patterns:
        for expanded in expand_braces(pat):
            for p in glob(os.path.join(root, expanded), recursive=True):
                rel = os.path.relpath(p, root).replace(os.sep, "/")
                if any(part in SKIP_DIRS for part in rel.split("/")):
                    continue
                found.add(rel)
    return found


def read(path, limit=400_000):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def is_git_repo(root):
    return os.path.isdir(os.path.join(root, ".git")) or bool(glob(
        os.path.join(root, ".git")))


def detect_stack(root, pkg):
    """Detect the stack, so any recommendation is grounded rather than generic."""
    marks = []
    deps = " ".join(pkg.get("dependencies", {}).keys()) + " " + \
           " ".join(pkg.get("devDependencies", {}).keys()) + " " + \
           read(os.path.join(root, "requirements.txt")) + \
           read(os.path.join(root, "pyproject.toml"))[:4000]
    for label, needle in STACK_MARKERS:
        if needle in deps:
            marks.append(label)
    for label, files in STACK_FILES:
        for f in files:
            if glob(os.path.join(root, f)):
                marks.append(label)
                break
    # Preserve order, drop dupes.
    seen, out = set(), []
    for m in marks:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out or ["unknown"]


def load_pkg(root):
    """Load package.json, tolerating absence AND malformed content.

    An audit must never refuse to run because one file is unparseable - that
    turns a diagnostic into a blocker, and a user bootstrapping an empty
    project is the most likely person to hit a half-written file. Degrade to an
    empty result and let the audit report what it can; the malformed file is
    itself a finding worth surfacing.
    """
    raw = read(os.path.join(root, "package.json"))
    if not raw.strip():
        return {}, None
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return {}, f"package.json is not valid JSON ({exc})"


def audit(root):
    pkg, pkg_error = load_pkg(root)
    scripts = pkg.get("scripts", {}) or {}
    ci_files = sorted(find_all(root, [
        ".github/workflows/*.yml", ".github/workflows/*.yaml",
        ".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile",
        ".circleci/config.yml",
    ]))
    ci_blob = "".join(read(os.path.join(root, f)) for f in ci_files)
    pkg_blob = json.dumps(scripts)

    report = {
        "repo": os.path.abspath(root),
        "is_git_repo": is_git_repo(root),
        "stack": detect_stack(root, pkg),
        "script_count": len(scripts),
        "layers": {},
        "warnings": [],
        "gaps": [],
    }

    if pkg_error:
        report["warnings"].append({
            "id": "unreadable-package-json",
            "severity": "medium",
            "message": pkg_error + ". Audit continued with scripts treated as "
                       "absent, so any gate wired only through npm will look "
                       "unwired.",
        })

    for key, name, patterns, evidence in LAYERS:
        hits = find_all(root, patterns)
        entry = {"name": name, "present": bool(hits), "files": len(hits)}
        if evidence is not None:
            entry["wired"] = any(t in ci_blob for t in evidence) or \
                             any(t in pkg_blob for t in evidence)
        report["layers"][key] = entry

    agents = sorted(find_all(root, [p for p in LAYERS[-1][2]]))
    agent_blob = "".join(read(os.path.join(root, f)) for f in agents)

    # Does any automation actually invoke an agent?
    invoked = bool(re.search(
        r"--agent\b|runSubagent|subagent|agents/qa|workflow_run"
        r"|GH_AGENT|claude\s+--print|codex\s+exec", ci_blob, re.I))
    # Some agent instructions say "file an issue" in prose; require intent.
    wants_filing = bool(re.search(
        r"file[^.\n]{0,60}(an?\s+)?(github\s+)?issue"
        r"|file[^.\n]{0,40}(a\s+)?bug[^.\n]{0,40}issue", agent_blob, re.I))

    report["layers"]["agent"]["filing_rules_written"] = wants_filing
    report["layers"]["agent"]["invoked_by_ci"] = invoked

    # ---- the finding that matters -------------------------------------
    if wants_filing and not invoked:
        report["warnings"].append({
            "id": "agent-never-invoked",
            "severity": "high",
            "message": "Agent file documents bug-filing rules, but NO workflow "
                       "invokes the agent. An uninvoked rule is a comment that "
                       "reads like a guarantee. The defect register stays empty.",
        })
    if wants_filing and not re.search(
            r"retest|re-?run the reproduction|only qa closes|close.{0,40}after",
            agent_blob, re.I):
        report["warnings"].append({
            "id": "no-retest-before-close",
            "severity": "medium",
            "message": "No retest-before-close policy. Issues get closed by "
                       "'fixed' rather than by evidence the fix holds.",
        })
    if not report["is_git_repo"]:
        report["warnings"].append({
            "id": "not-a-git-repo",
            "severity": "medium",
            "message": "Not a git repository. CI gates, PR flow and the defect "
                       "register all assume git.",
        })
    if report["is_git_repo"] and not ci_files:
        report["warnings"].append({
            "id": "no-ci",
            "severity": "high",
            "message": "Git repo but no CI workflow. Gates defined locally are "
                       "advisory; nothing stops a regression landing.",
        })

    for key, info in report["layers"].items():
        if info["present"] and info.get("wired") is False:
            report["gaps"].append(
                f"{info['name']} exists ({info['files']} files) but is not "
                f"referenced by any npm script or CI job - it cannot gate.")

    have = [k for k, v in report["layers"].items() if v["present"]]
    if not have:
        report["gaps"].append("No quality flow at all - full bootstrap needed.")
    return report


def render(rep):
    L = []
    L.append("QA bootstrap audit")
    L.append(f"  repo : {rep['repo']}")
    L.append(f"  stack: {', '.join(rep['stack'])}")
    L.append("")
    L.append("  layer                    present   wired")
    for info in rep["layers"].values():
        mark = "yes" if info["present"] else "NO"
        wired = info.get("wired")
        w = ("yes" if wired else "NO") if wired is not None else "-"
        count = f" ({info['files']})" if info.get("files") else ""
        L.append(f"  {info['name']:<24} {mark:<8} {w}{count}")

    if rep["warnings"]:
        L.append("")
        L.append("  WARNINGS")
        for w in rep["warnings"]:
            L.append(f"  [{w['severity'].upper()}] {w['id']}: {w['message']}")
    if rep["gaps"]:
        L.append("")
        L.append("  GAPS")
        for g in rep["gaps"]:
            L.append(f"  - {g}")
    L.append("")
    L.append("  Next: agree the frameworks with the user BEFORE scaffolding. "
             "Do not assume.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any warning is raised")
    args = ap.parse_args()

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2
    try:
        rep = audit(root)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(rep, indent=2) if args.json else render(rep))
    if args.strict and rep["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## Phase 3 - Unit and integration tests

Follow the method in your QA agent instructions. The order is by feedback
speed, cheapest gate first.

- Scope thresholds deliberately. A 100% gate is sustainable on pure logic
  (`src/models`, `src/domain`) and is a trap on components. Decide which and say
  why; if you choose a high bar, make it a **build failure**, not a review
  comment.
- Put thresholds in config, not in the workflow, so they cannot drift from what
  a developer runs locally.
- Write the first tests against real behaviour, not against the implementation.

## Phase 4 - Fakes and fixtures

Before any test needs a network. Stub the boundaries - auth, storage, external
API - in `tests/fixtures/`.

A suite that requires a live network gets skipped "temporarily" and stays that
way forever.

## Phase 5 - End-to-end tests

- Page objects from the first flow; they cost more up front and save more after
  three specs.
- Centralise selectors in one module so a markup change is one edit.
- Name tests after behaviour: `filtering by label hides non-matching cards`,
  not `test filterLabel`.
- Cover the risky areas, not just the happy path: empty states, error states,
  keyboard paths, and the narrowest viewport.

## Phase 6 - Accessibility gates

Compute contrast against **every background the foreground can appear on**,
including elevated surfaces and hover states. A token that clears 4.5:1 on the
page background and fails on a raised card is a live bug. A value that passes by
0.002 is a latent failure, not a pass.

If you use axe, let animations and transitions settle before scanning. A ratio
naming a colour that appears in no stylesheet is a composite, not a token.

## Phase 7 - CI wiring

Use the template below rather than writing YAML from memory. Copy the
`ci-gates` block, replace the `<...>` placeholders with this project's real
commands, and delete jobs that do not apply.

Keep these two rules, which the template encodes and comments:

- **Browser cache keys must be per-browser.** One key derived only from a
  lockfile means the first job populates the cache, every other job reports
  `cache-hit=true`, skips the browser install, and fails at launch with
  "Executable doesn't exist". That failure reads as a product bug and is not
  one. It has taken 90 of 94 tests.
- **The browser install must be unconditional.** Any `if:` on it means a cache
  hit silently skips installation - the same failure by a different route.

### Workflow templates

````markdown
# Templates

Copy-paste starting points for a project's quality flow. Each is a **template,
not a finished workflow** — replace `<...>` placeholders and delete what does
not apply. Copy only the gates the project actually has.

These ship **embedded inside `initqa.prompt.md`**, so there is nothing to fetch
and no URL that can go stale. Copy them straight out of the prompt.

| Template | Purpose |
|---|---|
| `ci-gates.yml` | Type-check + unit + accessibility + E2E on every PR |
| `defect-hunt.yml` | Invokes the QA agent: manual hunt, nightly backstop, CI triage |

If you are reading this file standalone on a machine, treat it as a copy of the
authoritative version in the prompt. A reconstructed workflow template is worse
than none, because it looks authoritative — if you cannot obtain the real one,
say so rather than writing YAML from memory.

---

## `ci-gates.yml`

Two rules that are not optional:

- **Browser cache keys must be per-browser.** One key derived only from a
  lockfile means the first job populates the cache and every other job reports
  `cache-hit=true`, skips `playwright install`, and fails at launch with
  "Executable doesn't exist". That reads as a product failure and is not one.
- **The browser install must be unconditional.** Any `if:` on it means a cache
  hit silently skips installation.

```yaml
name: Quality gates (PR)

on:
  pull_request:
    branches: [<default-branch>]

permissions:
  contents: read

# Superseded PR runs waste minutes; newer results are the ones that matter.
concurrency:
  group: pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: <lts>
          cache: npm
      - run: npm ci
      - run: <typecheck command>

  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: <lts>
          cache: npm
      - run: npm ci
      # Thresholds live in config, not here, so they cannot drift from what
      # a developer runs locally.
      - run: <unit + coverage command>

  accessibility:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: <lts>
          cache: npm
      - run: npm ci
      # A contrast rule that is only commented on is a rule that regresses.
      - run: <contrast / a11y command>

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: <lts>
          cache: npm
      - run: npm ci
      - uses: actions/cache@v4
        with:
          # PER-BROWSER. Two browsers sharing one key is the failure above.
          path: ~/.cache/ms-playwright-chromium
          key: ${{ runner.os }}-pw-chromium-${{ hashFiles('package-lock.json') }}
      - uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright-firefox
          key: ${{ runner.os }}-pw-firefox-${{ hashFiles('package-lock.json') }}
      # UNCONDITIONAL. No `if:` - see above.
      - name: Install browsers
        run: npx playwright install --with-deps chromium firefox
      - run: <e2e command>
```

> If the project merges to `main` and deploys, mirror these jobs into the deploy
> workflow rather than trusting the PR run alone - a branch-protection gap or a
> direct push bypasses it.

---

## `defect-hunt.yml`

Without this, documented filing rules are inert: an agent is only invoked when
something invokes it. That single omission is how a real repo ended a whole
development phase with a defect found, fixed, and never registered.

Requires a `COPILOT_*` secret in the repository. **Until it is set, comment out
the `schedule` trigger** - a nightly red build nobody reads trains everyone to
ignore red builds, which is the same failure as a gate nobody watches.

```yaml
name: Defect hunt (QA agent)

on:
  workflow_dispatch:
    inputs:
      focus:
        description: "What to hunt (blank = full sweep)"
        required: false
        type: string
      base_ref:
        description: "Hunt the diff since this ref"
        required: false
        type: string
  schedule:
    - cron: "17 3 * * *"   # off the hour: :00 is contended
  workflow_run:
    workflows: ["<ci workflow name>"]
    types: [completed]

permissions:
  contents: read
  issues: write          # it must file; it must NOT push

concurrency:
  group: defect-hunt-${{ github.ref }}
  cancel-in-progress: false

jobs:
  hunt:
    if: github.event_name != 'workflow_run'
    runs-on: ubuntu-latest
    timeout-minutes: 45
    env:
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-node@v4
        with:
          node-version: <lts>
          cache: npm
      - run: npm ci

      # Build BEFORE hunting. An unbuilt or stale bundle is the single most
      # common false bug: the agent reports defects in code that is not the
      # code being served.
      - run: <build command>

      - name: Confirm gh is authenticated
        run: gh auth status

      - name: Exploratory hunt
        env:
          COPILOT_ALLOW_ALL: "true"
        run: |
          FOCUS="${{ inputs.focus }}"
          BASE="${{ inputs.base_ref }}"

          # Single-line assignments on purpose: a multi-line double-quoted
          # scalar breaks the YAML block parser, and this is already inside a
          # block scalar.
          if [ -n "$BASE" ]; then
            SCOPE="Hunt for product defects introduced by the diff $BASE...HEAD. Focus on what changed and on what that change broke indirectly."
          elif [ -n "$FOCUS" ]; then
            SCOPE="Hunt for product defects in: $FOCUS Read the relevant spec first, then probe the risky paths."
          else
            SCOPE="Full exploratory sweep of the risky areas: responsive layout, popovers and sheets, drag and drop, persistence and debounce, offline and sync."
          fi

          # The heredoc body MUST be indented to this block's level. A body at
          # column 0 silently terminates the `run: |` block and the workflow
          # fails to parse.
          cat > prompt.md <<PROMPT_EOF
          $SCOPE

          1. This is DISCOVERY. Measure before judging: a finding you cannot
             state as "expected X, measured Y" is not confirmed.
          2. Do NOT edit product code and do NOT fix anything on this run.
          3. File every confirmed Medium/High defect with gh. Ask "which
             devices?" BEFORE "how bad?" - device scope separates the bands.
          4. Search for an existing issue first; comment rather than duplicate.
          5. Do not close or reopen anything.
          6. Finding nothing is a real result. Say so and list what you probed.
          PROMPT_EOF

          npx --yes @github/copilot@latest \
            -p "$(cat prompt.md)" \
            --agent <agent-name> \
            --allow-all-tools \
            --silent

  triage-ci-failure:
    # Only on an actual failure. On a green run there is nothing to triage, so
    # this must no-op rather than burn minutes re-reading a passing suite.
    if: >-
      github.event_name == 'workflow_run' &&
      github.event.workflow_run.conclusion == 'failure'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
      issues: write
    env:
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - name: Triage the failure
        env:
          COPILOT_ALLOW_ALL: "true"
        run: |
          cat > prompt.md <<PROMPT_EOF
          A CI run failed: ${{ github.event.workflow_run.html_url }}

          Decide which, and show the evidence:
          (a) PRODUCT defect - the app behaves wrongly. File it (Medium/High).
          (b) HARNESS problem - stale build output, a route-mock bypassed by CI
              mode, a debounce window, resource contention, or a flaky test.
              Do NOT file these.

          Rule out (b) FIRST. This repo has a documented history of mistaking
          (b) for (a).
          PROMPT_EOF

          npx --yes @github/copilot@latest \
            -p "$(cat prompt.md)" \
            --agent <agent-name> \
            --allow-all-tools \
            --silent
```

````

## Phase 8 - Project QA agent

Create `.github/agents/<name>.agent.md` (or your user-level equivalent) holding
**only what is true of this repository**: its commands, test counts, structure,
selectors, fakes, and the traps that have actually bitten here. Point it at your
user-level QA agent for the method - do not restate the method inside the repo
file, because a restatement will drift.

The `description` field is the only thing a router reads, so it must contain the
verbs that should route to the agent, including discovering defects. If it
lists nothing about finding bugs, the agent will never be summoned to find one.

Include this repo's impact bands for its own core flows, and its label list.

## Phase 9 - Defect register

Gates catch regressions in behaviour that is already asserted. They cannot
report a defect nobody wrote a test about.

Wire the filing path using the `defect-hunt` template: manual dispatch (after
unit tests are green and before writing E2E automation for a new feature), a
scheduled backstop, and triage after a CI failure.

- **File a Medium/High defect even when you are about to fix it.** Finding and
  fixing are separate acts; fixing does not discharge the obligation to
  register.
- **An issue closes only after a retest**, and only QA closes it. A commit that
  references an issue does not close it - that is what stops "fixed" from
  quietly meaning "believed".
- **Never end a run with a Medium/High finding that is neither filed nor
  explicitly reported as unfilable.**

The hunt needs a provider API key as a repository secret. **Until it is set,
comment out the scheduled trigger.** A nightly red build nobody reads trains
everyone to ignore red builds, which is the same failure as a gate nobody
watches.

Give it least privilege: permission to write issues, not to write contents.

## Phase 10 - Prove the gates gate

The step everyone skips, and the reason this flow exists.

1. Re-run the audit. `agent-never-invoked` must be gone, and every layer you
   added must report `wired: yes`.
2. Break something deliberately - a type error, a failing assertion, a contrast
   regression - and confirm each gate goes red. Revert.
3. Confirm the E2E job actually fails when a test fails. Do not assume.
4. Confirm the workflow triggers on the events you expect. A `branches: [main]`
   filter means pull requests targeting another branch run **nothing** and show
   as pending forever.
5. Report what each gate caught. A bootstrap that was never seen failing is
   untested scaffolding.

---

## Report

Finish with:

- The audit result before and after, and what changed.
- Every file created, by path.
- **Confirmation each gate was observed failing**, and what you broke to prove
  it.
- Anything deliberately deferred, and why.
- Anything you could not verify, stated plainly rather than implied.

Do not claim a gate works because you wrote it. Claim it works because you
watched it fail.
