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

### Preferred: `/initqa` (self-contained, no fetch at all)

`initqa.prompt.md` in this repo **embeds the audit script and both workflow
templates inline**. Drop it into your prompts folder and run `/initqa`:

| Platform | Location |
|---|---|
| Windows | `%APPDATA%\Code\User\prompts\` |
| macOS | `~/Library/Application Support/Code/User/prompts/` |
| Linux | `~/.config/Code/User/prompts/` |

The command name comes from the filename, so the file must be called
`initqa.prompt.md`. It needs no network and no install, which is why it is the
recommended path — see "Why embed rather than fetch" below.

### Keeping it current: `qa_toolkit_refresh.py`

A dropped-in file drifts. `qa_toolkit_refresh.py` compares the version marker
inside your installed prompt against the published `VERSION` and tells you
only when something changed.

```bash
python qa_toolkit_refresh.py             # silent unless an update exists
python qa_toolkit_refresh.py --json      # state, local and remote version
python qa_toolkit_refresh.py --apply     # download and install
python qa_toolkit_refresh.py --strict    # exit 1 unless current
```

It auto-detects the installed prompt; `--dest` overrides the path.

| State | Meaning | Caller should |
|---|---|---|
| `current` | Matches published | Say nothing, carry on |
| `stale` | Newer version exists | Offer it, **but never block** |
| `offline` | No network | Say nothing, carry on exactly as before |
| `ambiguous` | A server answered unusably | Treat as `stale`, mention in one line |
| `missing` | No version marker | Carry on silently |

Three deliberate properties:

- **It never blocks.** No network is the expected state on a train or behind a
  proxy. A bootstrap that fails offline is a bootstrap nobody runs.
- **Offline is silent, and always exits 0.** Only `--strict` returns non-zero,
  so it is safe in a pipeline.
- **Untrustworthy is never reported as `current`.** An HTTP 404, a rate limit
  or unparseable JSON becomes `ambiguous`, not "up to date". A redundant
  "an update is available" line costs one line; silently believing you are
  current is the failure this toolkit exists to prevent.

`--apply` refuses to overwrite your prompt with anything that lacks frontmatter
and a version marker, so a truncated download cannot destroy a working file.

### Why embed rather than fetch

Measured on this repository: after a commit landed on `main`, the
`raw.githubusercontent.com`/main URL kept serving the *previous* file for an
extended period, and a `?cb=<timestamp>` cache-buster **did not defeat it**:

| URL form | Result after a push |
|---|---|
| `.../main/qa_bootstrap_audit.py` | stale — old content |
| `.../main/...py?cb=12345` | stale — cache-buster ignored |
| `.../<SHA>/qa_bootstrap_audit.py` | current |

`main` gives an agent a script that looks fine and quietly lacks every recent
fix — a stale diagnostic is worse than a missing one, because a missing one is
visibly missing. So the refresh helper compares versions through the **GitHub
contents API**, which reflects the current ref, rather than fetching a raw file.

If you must fetch standalone files, pin a SHA and keep the filename — the tests
`import qa_bootstrap_audit`, so renaming it breaks them, and a suite that
cannot run is worse than none. Treat a fetch failure as a hard stop; never
reconstruct a tool from memory.

## Bumping the version

`VERSION` holds a single token (`v1`). It is the single source of truth for the
marker embedded in the prompt:

```bash
# edit VERSION, then:
python build_prompt.py
python -m unittest discover
```

`build_prompt.py` reads `VERSION` rather than hardcoding it, and
`test_prompt.py` asserts the built prompt carries that exact marker — so a bump
cannot be forgotten when the prompt is rebuilt.

## Tools

### `qa_toolkit_refresh.py` — freshness check

See "Keeping it current" above. Tri-state, non-blocking, standard library only.

```bash
python qa_toolkit_refresh.py             # silent unless an update exists
python qa_toolkit_refresh.py --apply     # download and install
```

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
