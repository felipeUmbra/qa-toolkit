"""Build initqa.prompt.md with the audit script embedded verbatim.

The script is inlined from the tested source rather than copied by hand, so the
prompt cannot drift from the file that has 31 passing tests behind it. A
hand-copied copy would be a second source of truth and would eventually be
wrong without anyone noticing.

VERSION drives the freshness marker that qa_toolkit_refresh.py compares. It is
read from the single VERSION file rather than hardcoded here, so bumping the
version cannot be forgotten when the prompt is rebuilt.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, "qa_bootstrap_audit.py")
VERSION_FILE = os.path.join(HERE, "VERSION")


def read_version():
    with open(VERSION_FILE, encoding="utf-8") as fh:
        version = fh.read().strip()
    if not version:
        raise SystemExit("VERSION is empty - refusing to build an unversioned prompt")
    return version


VERSION = read_version()

# Fence must be longer than any backtick run inside the embedded content.
def fence_for(text, base="```"):
    n = base
    while ("\n" + n) in ("\n" + text) or text.startswith(n):
        n += "`"
    return n

with open(AUDIT, encoding="utf-8") as fh:
    audit_src = fh.read().rstrip("\n")

with open(os.path.join(HERE, "templates.md"), encoding="utf-8") as fh:
    templates = fh.read()

FENCE = fence_for(audit_src)
TFENCE = fence_for(templates)

BODY = '''---
description: "Set up this project's quality flow from scratch - interview the user, then scaffold tests, accessibility gates, CI, a project QA agent, and a defect register in the right order."
argument-hint: "[optional: path to audit, defaults to the workspace]"
agent: "agent"
tools: ["codebase", "search", "usages", "problems", "editFiles", "createFile", "runCommands", "runTasks", "runTests", "testFailure", "terminalLastCommand", "terminalSelection", "getTaskOutput", "killTerminal", "notebooks", "githubRepo", "github_text_search", "fetch", "vscode/askQuestions"]
---

# Initialise this project's quality flow
<!-- toolkit-version: {VERSION} -->
Your job is to stand up a working quality flow for THIS repository, in the
right order, and to prove each piece actually gates. Work through the phases
below in order. Do not skip phase 1 - asking is not optional.

Two rules govern everything else:

- **Never scaffold over something that already exists.** Phase 1 exists to
  prevent a second runner or a duplicated CI job.
- **A gate that has never been seen failing is not a gate.** Phase 9 exists
  because scaffolding nobody verified is decoration.

---

## Phase 0 - Check this prompt is current (non-blocking)

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

### The audit script

Save this verbatim as `scripts/qa_bootstrap_audit.py`. It is pure standard
library - Python 3.8+, no install, no dependencies.

{FENCE}python
{audit_src}
{FENCE}

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

{TFENCE}markdown
{templates}
{TFENCE}

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
'''

out = BODY.replace("{FENCE}", FENCE).replace("{audit_src}", audit_src) \
          .replace("{TFENCE}", TFENCE).replace("{templates}", templates) \
          .replace("{VERSION}", VERSION)

# Strip the outer .format() braces used above; verify none leaked.
for leaked in ("{FENCE}", "{audit_src}", "{TFENCE}", "{templates}", "{VERSION}"):
    assert leaked not in out, f"placeholder leaked: {leaked}"

# The freshness marker is what qa_toolkit_refresh.py compares against a local
# copy. If it is missing, a stale install is indistinguishable from a current
# one, which is the exact failure this marker exists to prevent.
marker = "<!-- toolkit-version: %s -->" % VERSION
assert marker in out, "version marker missing from generated prompt"

target = os.path.join(HERE, "initqa.prompt.md")
with open(target, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(out)
print(f"wrote {target}")
print(f"  {len(out.splitlines())} lines, {len(out)} chars")
print(f"  fence: {FENCE!r} / {TFENCE!r}")
print(f"  version: {VERSION}")
