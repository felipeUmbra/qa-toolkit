# qa-toolkit

Small, dependency-free tools for standing up and checking a project's quality
flow. Hosted so any machine, any repo, any agent can use them.

**Pure standard library.** Python 3.8+. No install, no venv, no `pip`.

## Why these exist

A repo can have tests, gates, CI, an agent file documenting bug-filing rules —
and still have a defect register that is empty and gates that cannot fail. Every
tool here exists because that specific failure happened in a real repository:

| Failure | What went wrong | What catches it |
|---|---|---|
| **Uninvoked rule** | Agent documented "file every Medium/High defect"; no workflow ever invoked the agent. A defect sat in the **first commit**, survived ~49 commits, and was found and fixed without ever being registered. | `qa_bootstrap_audit.py` → `agent-never-invoked` |
| **Unwired gate** | A whole test layer existed and was wired into no npm script and no CI job. It could not fail anything. | `qa_bootstrap_audit.py` → "cannot gate" gap |
| **Shared cache key** | Two CI jobs shared one browser cache key. First job populated it; the rest skipped `playwright install` and failed with "Executable doesn't exist" — 90 of 94 tests, reading as a product failure. | `templates.md` + `test_templates.py` |
| **Triage that fires on green** | A CI-failure triage job would re-read a *passing* suite every run. | `test_templates.py` → `test_defect_hunt_triage_only_runs_on_failure` |

## Fetching these from the agent

Pin to a commit SHA. **Do not fetch from `main`.**

```
https://raw.githubusercontent.com/felipeUmbra/qa-toolkit/<SHA>/qa_bootstrap_audit.py
```

**Keep the filename.** Save it as `qa_bootstrap_audit.py`. The test modules
`import qa_bootstrap_audit`, so renaming it makes them fail to import — and a
test suite that cannot run is worse than none. This was found by simulating a
fresh machine and renaming the file, which is the only way to find it.

Verified behaviour: after a commit landed on `main`, the `main` URL kept serving
the *previous* file for an extended period, and a `?cb=<timestamp>` cache-buster
**did not defeat it**. The SHA-pinned URL served the new content immediately.

| URL form | Result after a push |
|---|---|
| `.../main/qa_bootstrap_audit.py` | stale — old content |
| `.../main/...py?cb=12345` | stale — cache-buster ignored |
| `.../<SHA>/qa_bootstrap_audit.py` | current |

So `main` gives an agent a script that looks fine and quietly lacks every recent
fix. Pin the SHA, and treat a fetch failure as a hard stop — never reconstruct
the tool from memory, because a reconstructed script carries the bugs this
toolkit exists to remove.

## Tools

### `qa_bootstrap_audit.py` — read-only

```bash
python qa_bootstrap_audit.py                 # audit cwd
python qa_bootstrap_audit.py /path/to/repo
python qa_bootstrap_audit.py --json          # machine-readable
python qa_bootstrap_audit.py --strict        # exit 1 on any warning
```

Detects, per layer: present / wired, plus the stack. Warns on `agent-never-invoked`,
`no-retest-before-close`, `no-ci`, `not-a-git-repo`.

It runs no tests, opens no network connection, and writes nothing — safe on any
repo, including one you have never seen. **Run it before scaffolding anything**;
half the value is not building a second runner on top of an existing one.

### `templates.md` — copy-paste starting points

`ci-gates.yml` (type-check + unit + a11y + E2E on every PR) and
`defect-hunt.yml` (manual hunt / nightly backstop / CI triage). Placeholders
marked `<...>`; delete what does not apply.

A template that does not parse is worse than none, because it gets copied
verbatim and only fails in CI.

## Tests

```bash
python -m unittest discover -v      # all
python test_qa_bootstrap_audit.py   # audit only
python test_templates.py            # templates only
```

No pytest dependency on purpose: these must run anywhere, including a machine
that has only the standard library.

`test_qa_bootstrap_audit.py` pins a bug that shipped once already: **Python's
`glob` does not expand braces**, so `**/*.{js,ts}` silently matched nothing and
the audit reported a healthy repo as untested. A silent zero-match is
indistinguishable from "absent" — the worst possible failure for a diagnostic,
because it under-reports and is therefore trusted. The fix is explicit brace
expansion with a regression test.

`test_templates.py` parses every YAML fence and asserts the structural
invariants that are easy to break by hand: per-browser cache keys, an
unconditional browser install, three triggers, `issues: write` without
`contents: write`, triage gated on failure, and heredoc bodies indented inside
their `run: |` block.

## Known limits

- Detects *presence* and *wiring*, not correctness. It cannot tell you a test
  asserts nothing useful — coverage percentage cannot either.
- "No test names this file" is weak evidence. Suites usually drive the UI
  through selectors, not source paths.
- `--strict` warns; it does not fix. It is a signal for a human.
- The hosted URLs below must stay reachable. If one 404s, **say so** rather than
  writing the tool from memory — a reconstructed script will carry the bugs this
  toolkit exists to remove.
