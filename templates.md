# Templates

Copy-paste starting points for a project's quality flow. Each is a **template,
not a finished workflow** — replace `<...>` placeholders and delete what does
not apply. Copy only the gates the project actually has.

Fetched by the QA agent's bootstrap step. If a URL 404s, the agent must say so
rather than fall back to writing YAML from memory.

| Template | Purpose |
|---|---|
| `ci-gates.yml` | Type-check + unit + accessibility + E2E on every PR |
| `defect-hunt.yml` | Invokes the QA agent: manual hunt, nightly backstop, CI triage |

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
