# qa-toolkit

Stand up a project's quality flow — tests, accessibility gates, CI, a QA agent
and a defect register — from a single command, then keep it honest.

**Pure standard library.** Python 3.8+. No install, no venv, no `pip`.

---

## Quickstart

### 1. Get the file

Download **`initqa.prompt.md`** from this repo — that one file is the whole
toolkit. The audit script and both workflow templates are embedded inside it,
so there is nothing else to fetch and no URL that can go stale.

The **easiest way** is to fetch the refresh helper and let it install the
prompt for you. It picks the right file, finds your prompts folder, and
verifies what it downloaded:

```bash
curl -O https://raw.githubusercontent.com/felipeUmbra/qa-toolkit/main/qa_toolkit_refresh.py
curl -O https://raw.githubusercontent.com/felipeUmbra/qa-toolkit/main/qa_bootstrap_audit.py
curl -O https://raw.githubusercontent.com/felipeUmbra/qa-toolkit/main/initqa.prompt.md
python qa_toolkit_refresh.py --apply
```

Or download `initqa.prompt.md` straight from the repo page in your browser.
Keep the filename exactly as `initqa.prompt.md` — the command name comes
from it.

> **A note on `main` URLs.** This repo has *measured* the raw `main` URL
> serving the previous file after a push, with a `?cb=<timestamp>` cache-buster
> failing to defeat it. If you want a guaranteed-current file rather than
> probably-current, replace `main` with a commit SHA:
>
> ```bash
> curl -O https://raw.githubusercontent.com/felipeUmbra/qa-toolkit/6c12a229c6d5569e77d3b7c5f91ecaff97986464/initqa.prompt.md
> ```
>
> If a fetch fails, **say so** rather than reconstructing the file — a
> hand-written replacement carries the very bugs this toolkit exists to
> remove.

### 2. Put it where VS Code looks for prompts

| Platform | Folder |
|---|---|
| **Windows** | `%APPDATA%\Code\User\prompts\` |
| **macOS** | `~/Library/Application Support/Code/User/prompts/` |
| **Linux** | `~/.config/Code/User/prompts/` |

Create the folder if it does not exist.

```powershell
# Windows, one-liner
mkdir "$env:APPDATA\Code\User\prompts" -Force
Copy-Item initqa.prompt.md "$env:APPDATA\Code\User\prompts\"
```

### 3. Run it

1. Open your project folder in VS Code.
2. Open Chat (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>I</kbd>).
3. Type **`/initqa`** and pick it from the list.

> **If `/initqa` does not appear**, reload the window
> (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> → *Developer: Reload Window*).
> The command is discovered at startup, so a prompt added mid-session will not
> show up until you reload. Also confirm the file is in your **user** prompts
> folder, not inside the project.

You can pass a path: `/initqa ../another-repo`.

### 4. Answer the questions

Phase 1 asks about the choices it genuinely cannot infer — test runner, E2E
driver, accessibility approach, viewports, PR policy, external APIs, and
whether defects get filed automatically. Each question offers at most three
options with a recommendation. Everything else it reads from your repo.

### 5. Watch it work

The run ends with Phase 10, which **breaks something on purpose** and confirms
each gate turns red, then reverts. That step is the point: a gate nobody has
seen fail is not a gate.

---

## Requirements

**None for the prompt itself** — `/initqa` is a Markdown file, so the interview
and the scaffolding phases work with no runtime installed at all.

**Python 3.8+ is needed for two things only:**

| Needs Python | Does not |
|---|---|
| The Phase 0 freshness check | The interview (phase 1) |
| The Phase 2 quality audit | Scaffolding tests, E2E, a11y, CI, and agents |
| | Phase 10, proving the gates gate |

If you have no Python, `/initqa` says so and falls back to auditing with `node`
— which your project already has, since it is a JavaScript project — or by
reading the repo directly. Nothing is installed without asking you first.

> **A trap worth knowing.** On Windows, `python` can resolve to the Microsoft
> Store alias, which prints nothing and **exits 0**. That looks exactly like a
> clean audit of a repo with no quality flow. The prompt checks for an
> interpreter first and is explicitly forbidden from reporting an audit that
> never ran as a clean result — but if you run the audit by hand, verify you
> got real output, not silence.

---

## What `/initqa` creates in your project

Nothing is written until Phase 2 has read what you already have, so you never
get a second test runner or a duplicate CI job. In a typical project you get:

| Path | What it is | Phase |
|---|---|---|
| `scripts/qa_bootstrap_audit.py` | Read-only quality audit | 2 |
| `tests/` + a test config | Unit/integration suite, thresholds in config | 3 |
| `tests/fixtures/` | Fakes for auth, storage, external APIs | 4 |
| `e2e/` or `tests/e2e/` | E2E specs, page objects, one selectors module | 5 |
| a11y checks | `axe-core` scan + a contrast script | 6 |
| `.github/workflows/ci-gates.yml` | Type-check, unit, a11y, E2E on every PR | 7 |
| `.github/workflows/defect-hunt.yml` | Manual hunt, nightly backstop, CI triage | 7 |
| `.github/agents/<name>.agent.md` | **Your** project QA agent — repo facts only | 8 |
| GitHub labels + issue templates | So a defect can actually be filed | 9 |

Exact paths follow your stack's conventions — the prompt reads your repo rather
than imposing a layout. It also wires `package.json` scripts so the gates are
runnable locally, not only in CI.

### The two workflows

**`ci-gates.yml`** runs on every pull request. Two rules in it are not optional:

- **Browser cache keys must be per-browser.** One key derived from a lockfile
  means the first job populates the cache and every other job reports
  `cache-hit=true`, skips the browser install, and fails at launch with
  `Executable doesn't exist`. That reads as a product failure and is not one.
  It has taken 90 of 94 tests.
- **The browser install must be unconditional.** Any `if:` on it means a cache
  hit silently skips installation — the same failure by a different route.

**`defect-hunt.yml`** is what makes the defect register reachable. It invokes
the QA agent three ways: on demand, on a schedule as a backstop, and after a CI
failure. Without a workflow that actually calls the agent, bug-filing rules are
a comment that reads like a guarantee — which is exactly how a real defect sat
in the first commit of a real repo, survived ~49 commits, and was fixed without
ever being registered.

> Until you add the agent's API key as a repository secret, **comment out the
> scheduled trigger.** A nightly red build nobody reads trains everyone to
> ignore red builds, which is the same failure as a gate nobody watches.

---

## Keeping it up to date

Your installed file drifts, because this repo gains fixes and the copy on disk
does not. Fetch `qa_toolkit_refresh.py` from this repo and run it:

```bash
python qa_toolkit_refresh.py             # silent unless an update exists
python qa_toolkit_refresh.py --json      # state, local and remote version
python qa_toolkit_refresh.py --apply     # download and install the new prompt
```

It finds your installed prompt by itself.

| State | What it means | What to do |
|---|---|---|
| `current` | You match this repo | Nothing |
| `stale` | A newer version exists | Run with `--apply` |
| `offline` | No network, or unreachable | Nothing — carry on |
| `ambiguous` | A server answered but the answer is unusable | Treat as `stale` |
| `missing` | No version marker in the file | Nothing |

`/initqa` runs this check itself as **Phase 0**, and it is deliberately
non-blocking: up to date, offline, or an update offered — the flow continues
either way. A bootstrap that fails because a laptop is on a train is a
bootstrap nobody runs.

Two details worth knowing:

- **It compares versions through the GitHub contents API**, not a raw file.
  Measured on this repo, the raw `main` URL kept serving the *previous* file
  after a push, and a `?cb=<timestamp>` cache-buster did not defeat it. A stale
  tool is worse than a missing one, because a missing one is visibly missing.
- **Untrustworthy is never reported as `current`.** A 404, a rate limit, or an
  unparseable response becomes `ambiguous`, not "up to date". A redundant
  "an update is available" line costs one line; silently believing you are
  current is the failure this toolkit exists to prevent.

---

## Agent files

The QA agent is tracked here too, in [`agents/`](agents/README.md):

| File | Scope |
|---|---|
| `agents/user/qa.agent.md` | Framework **doctrine** — installs to `%APPDATA%\Code\User\agents\` |
| `agents/project-example/kboard.qa.agent.md` | One project's **facts** — installs to `<repo>/.github/agents/` |

They are deliberately **not** copies. Doctrine that lives in a repo stops being
true elsewhere and gets maintained twice; facts that live globally stop being
true the moment there is a second project. A repo file that restates the method
will drift, so `test_agents.py` fails the build when one does.

Tracking them here is what makes them recoverable — a file that only exists in
a user profile has no history and no way back.

---

## Other tools

Use these directly if you want to check a repo without running the whole flow.

### `qa_bootstrap_audit.py` — read-only audit

```bash
python qa_bootstrap_audit.py                 # audit the current folder
python qa_bootstrap_audit.py /path/to/repo
python qa_bootstrap_audit.py --json          # machine-readable
python qa_bootstrap_audit.py --strict        # exit 1 on any warning
```

Reports each quality layer as **present** or **wired** — an unwired gate cannot
fail, however many files it has. Warns on `agent-never-invoked`,
`no-retest-before-close`, `no-ci`, `not-a-git-repo`.

It runs no tests, opens no network connection, and writes nothing — safe on any
repo, including one you have never seen. **Run it before scaffolding anything**;
half the value is not building a second runner on top of an existing one.

### `templates.md` — the two workflows

`ci-gates.yml` and `defect-hunt.yml` with placeholders marked `<...>`. Also
embedded in `initqa.prompt.md`. A template that does not parse is worse than
none, because it gets copied verbatim and only fails in CI.

---

## Why these exist

Each tool answers a failure that actually happened in a real repository:

| Failure | What went wrong | What catches it |
|---|---|---|
| **Uninvoked rule** | Agent documented "file every Medium/High defect"; no workflow ever invoked the agent. A defect sat in the **first commit**, survived ~49 commits, and was found and fixed without ever being registered. | `qa_bootstrap_audit.py` → `agent-never-invoked` |
| **Unwired gate** | A whole test layer existed, wired into no npm script and no CI job. It could not fail anything. | `qa_bootstrap_audit.py` → "cannot gate" gap |
| **Silent zero-match** | Python's `glob` does not expand braces, so `**/*.{js,ts}` matched nothing and the audit reported a healthy repo as untested. Under-reporting is trusted, so it is the worst failure a diagnostic can have. | `test_qa_bootstrap_audit.py` → explicit brace expansion |
| **Shared cache key** | Two CI jobs shared one browser cache key; 90 of 94 tests failed at launch, reading as a product failure. | `templates.md` + `test_templates.py` |
| **Triage on green** | A CI-failure triage job re-read a *passing* suite every run. | `test_templates.py` → triage gated on failure |
| **Silent stale copy** | A tool fetched from a URL that serves old content looks authoritative and quietly lacks every recent fix. | embed instead of fetch + `qa_toolkit_refresh.py` |

---

## Development

```bash
python -m unittest discover -v      # 70 tests
python build_prompt.py              # regenerate initqa.prompt.md
```

`initqa.prompt.md` is **generated**. Edit `build_prompt.py`, not the output —
a hand-edited prompt is reverted on the next build, and the tests will catch
you. The build reads `VERSION` rather than hardcoding it and inlines the audit
script verbatim, so the prompt cannot drift from the file that has tests behind
it.

To release a new version:

```bash
# edit VERSION, then:
python build_prompt.py
python -m unittest discover
git commit -am "release v2" && git push
```

`test_prompt.py` asserts the built prompt carries the exact `VERSION` marker,
so a bump cannot be forgotten when the prompt is rebuilt.

### Test layout

| File | Covers |
|---|---|
| `test_qa_bootstrap_audit.py` | the audit, including the brace-expansion bug |
| `test_templates.py` | every YAML fence parses; per-browser cache keys; unconditional install; three triggers; `issues: write` without `contents: write`; triage gated on failure; heredoc indentation |
| `test_prompt.py` | frontmatter, fence balance, embedded script is byte-identical and still executes, builder/artifact agreement, interpreter and writability preflights |
| `test_qa_toolkit_refresh.py` | current / stale / offline / ambiguous / missing, install safety, first-time install |
| `test_agents.py` | the tracked agent files: routing verbs survive, user/project split is respected, no doctrine copied between them |

No pytest dependency on purpose — these must run anywhere, including a machine
with only the standard library.

---

## Known limits

- The audit detects **presence and wiring, not correctness**. It cannot tell you
  a test asserts nothing useful; coverage percentage cannot either.
- "No test names this file" is weak evidence. Suites usually drive the UI
  through selectors, not source paths.
- `qa_bootstrap_audit.py --strict` warns; it does not fix. It is a signal for a
  human.
- The refresh check needs network access to be useful. Offline it reports
  `offline` and changes nothing, which is intentional.
- If a hosted file 404s, **say so** rather than reconstructing the tool from
  memory — a hand-written replacement carries the very bugs this toolkit exists
  to remove.

## Licence

MIT.