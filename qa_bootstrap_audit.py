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
    raw = read(os.path.join(root, "package.json"))
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: package.json is not valid JSON: {exc}")


def audit(root):
    pkg = load_pkg(root)
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
