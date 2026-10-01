# Agent files

The QA agent exists in **two places, on purpose**. They are not copies of each
other and must not be made into copies.

| File | Install to | Holds |
|---|---|---|
| `user/qa.agent.md` | `%APPDATA%\Code\User\agents\qa.agent.md` | Framework **doctrine**: method, order, traps. True in any repo. |
| `project-example/kboard.qa.agent.md` | `<repo>/.github/agents/qa.agent.md` | One project's **facts**: commands, test counts, selectors, local traps. |

## Why the split

Doctrine that lives in a repo stops being true the moment it loads somewhere
else, and gets maintained twice. Facts that live in the global agent stop being
true the moment a second project appears.

So:

- **Keep the method here** (`user/`), maintained once.
- **Keep the specifics in the repo** (`project-example/`), versioned with the
  code they describe.
- **Never restate the method inside a repo file.** A restatement drifts out of
  sync with the global file, and then you have two sources of truth and no way
  to tell which one is right.

When the global agent loads in a repo that ships its own QA agent, **the repo
file wins** on any conflict. The global file supplies the method; the repo file
supplies the specifics.

## Installing

```powershell
# user scope - applies to every project
Copy-Item agents\user\qa.agent.md "$env:APPDATA\Code\User\agents\"

# project scope - applies to one repo only
Copy-Item agents\user\qa.agent.md <repo>\.github\agents\qa.agent.md
```

Copying a file is one line; the point of tracking it here is that it can be
**recovered**. A file that only exists in a user profile has no history and no
way back once it is lost.

## Editing

1. Edit the live file where it is used.
2. Copy it back here.
3. Commit — and say in the message *why*, not just what.

```powershell
Copy-Item "$env:APPDATA\Code\User\agents\qa.agent.md" agents\user\qa.agent.md -Force
git add agents/ && git commit -m "..."
```

Edits are only really made once they are committed, so do not leave this step
to the end of a session.

## What the agent holds

- **The order, and why it is that order** — cheapest gate first, audit before
  scaffolding, interviews before assumptions.
- **Bootstrap doctrine** — `/initqa` as the recommended path, the writability
  and interpreter preflights, and the rule that a stale tool is worse than none.
- **Defect discovery and filing** — explore for bugs, file Medium/High even when
  about to fix, and close only after a retest.
- **Framework traps** — Playwright timeouts, the service-worker/route-mocking
  trap, per-browser cache keys, layout measurement, a11y scanning.

## Two failure modes it is built to prevent

**An uninvoked rule.** The agent documents that defects must be filed; no
workflow ever calls the agent. The rule reads like a guarantee and the register
stays empty. A real defect sat in the first commit of a real repo, survived ~49
commits, and was found and fixed without ever being registered.
`qa_bootstrap_audit.py` reports this as `agent-never-invoked`.

**A gate never seen failing.** Scaffolding that nobody verified is decoration.
The bootstrap ends by breaking something on purpose and confirming each gate
turns red.

## Keeping the two in step

A repo agent should *point at* the global one for method, not repeat it. If the
repo file starts explaining how to diagnose a flake, that belongs in
`user/qa.agent.md` instead.

When you learn something general in one repo, write it here **without naming
the repo**. The lesson generalises; the example does not.