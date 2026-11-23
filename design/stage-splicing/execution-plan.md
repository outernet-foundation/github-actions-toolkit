# Stage-splicing execution plan

Linear steps through the rebase and the review gate, then the consumer porting
knowledge beyond it. No rationale. Where a value is ruled by the ADR it is
spelled here verbatim.
Commit discipline per `AGENTS-SHARED.md` throughout: commit at each step boundary,
prose and code in separate commits, one subject line under 72 characters, no trailers.

## Session state (read first, update as work lands)

This section is the entry point. A session that lands work updates it as that work is
committed and before it stops, as its own prose commit, and removes what no later step
depends on. It records the phases committed and the tip SHA, where to resume, the values
of `T1` and `T2` once they exist, every deviation from the steps below, and every open
item a later step depends on. Nothing loads this file automatically, so the handoff
message tells the operator to open the next session on it.

- The env-extension session landed (operator unparked the branch, 2026-11-25): the branch
  was rebased in place onto `dev` at `bae9203` (dev had moved two commits past the branch's
  `91f416f` base: the environment-preset strike, touching only `build-unity.yml` — which this
  branch deletes, resolved modify/delete by deleting — and `AGENTS.md` — which this branch
  rewrites wholesale, resolved by taking the branch side). The rebased tree is byte-identical
  to the pre-rebase tip (matching tree hashes), so the rebase is content-neutral. The
  extension then landed as consumer env bindings: a channel-keyed `env:` map on each
  `publish.yml` job entry (`env name -> repo-secret name`), spliced by the generator as
  job-level `env` on every job of that entry (injected after the transform, because the
  secret rewriter would treat the final repo-secret names as stage slots), additive-only
  with loud collisions against any key the stage's job sets through job env,
  `defaults.run.env`, or step env (those scopes outrank job env and would silently shadow
  the entry), `GITHUB_`/`RUNNER_`-prefixed names refused at config load, and a `uses` entry
  taking no `env`. This is the consumer's arbitrary env threading riding the secrets channel
  end to end: the generated jobs live in the consumer's own workflow file, where its repo
  secrets are nameable directly, and neither the toolkit nor any domain stage learns a
  consumer's variable names. Backup branch: `fork-contribution-lane-pre-env-extension` at
  `f8c0245` (the pre-rebase tip, also `origin/fork-contribution-lane` — the rebase rewrites
  published history, push is operator-owned). Goldens regenerated with `WRITE_GOLDEN=1`
  (the fixture publish config carries pr/dev env maps; the release goldens show dev-only
  injection and untouched stable jobs). Verified at the tip: 318 pytest (the prior session's
  348 count does not reproduce on the identical tree, the difference is that session's
  environment, not content), ruff, format, basedpyright, lint-workflows,
  `generate-github-workflows --check`, `sync-contributor-docs --check` — all green.
  The review pass (same session) then audited the extension against the code-quality and
  commenting guides and fixed it in place: the env field's narration comment deleted with
  the type aliases carrying the shape, the collision check flattened from a nested if into
  conditional-expression narrowing that follows the needs-check pattern, and the
  single-call-site shadowed_env_keys helper inlined into the splice. The branch was then
  rebased into the rebase guide's five-kind shape: the AGENTS.md contract row rides the
  agent-doc commit, the session record rides the other-prose commit, and the extension
  code commit sits directly after the generator verb commit. The reshape is content-neutral
  (empty tree diff across it).
  Resume at step 36 (`operator:`) unchanged: review the rebased branch plus this extension.
- The review-shape pass landed (third sitting, operator ruling): the three hand-authored
  underscore files are excised from the rerun-merge-system commit — they were an
  add-then-replaced pair once self-adoption landed (the shape rebase owed no excision
  because the original branch never replaced them), so the repo's own lane files now
  appear exactly once, as pure additions of generated output at the self-adoption
  commit. Between the machinery commit and self-adoption the repo carries no integrate
  file of its own — sanctioned redlessness per the guide's Green section, and nothing
  between those positions references the underscore files. AGENTS.md no longer
  references any file riding the trailing prose commit (seven ADR citations stripped,
  the asserted laws kept inline), squashed into the agent-doc commit. The trailing
  prose commits are squashed into one.
- The emitter rework landed (operator ruling, 2026-11-23 second sitting): the branch is
  rebuilt in place on `fork-contribution-lane` (16 commits over `origin/dev`), replacing
  the Python-constructed spine and its hand-rolled serializer with authored YAML
  templates (`src/github_actions_toolkit/templates/`, five files, package data) filled
  by token substitution — the design sketch's own "spine templates wrap the fan" intent,
  never previously ruled out. `emitting.py` and `splicing.py` are gone: everything lives
  in `verbs/generate_github_workflows.py` (stage acquisition, transforms, template
  filling, drift check), one module for one verb per the code-quality guide's inline
  cascade. The old four-commit generator slice (jobs schema, splicing, emitting,
  verb) is ONE commit; the jobs schema rides it too (a config accepting `jobs:`
  nothing consumes is a nonsense intermediate). Three shipped defects died with the
  serializer: the `ready_for_view` wake-type typo (now `ready_for_review`, authored
  once in the integrate template), the `github.event_name == 'pull_request_target'`
  conjunct the old golden asserted into always-false push-pass jobs (fixtures now
  carry context-neutral stage ifs; a stage `if` must hold in every target context),
  and the `build-dev`/`build-main` naming inversion — the release template's delivery
  jobs are `prerelease`/`release` needing the `dev-*`/`stable-*` fan tails, and
  AGENTS.md's sentence now names that shape (amended in the agent-doc commit,
  spec-first). Self-adoption landed on this branch rather than deferring to T2
  (operator ruling): `publish.yml` carries a bare `jobs:` key (strictyaml forbids
  flow mappings, so the empty map spells as the bare key; the config coerces `""`
  to `{}`), the generator's self mode wrote the four underscore files (`_preflight.yml`
  is new), and `sync-contributor-docs` write mode stood up `CONTRIBUTING.md` and
  `.github/PULL_REQUEST_TEMPLATE.md` in the repo root because the lane pair going
  live activates that gate for this repo itself. The contributor-docs canonical now
  rides the sync-contributor-docs verb commit (the verb and its data are one logical
  change; the old split left five tests red at every intermediate). Backup branch:
  `fork-contribution-lane-pre-emitter-rework` at `506a995` (the pre-rebase backup
  `6654156` lives only in the other sandbox/remote — unreachable here). Verified at
  the tip: 312 pytest, ruff, format, basedpyright, lint-workflows (over the
  generated underscore files), `generate-github-workflows --check` (the fixed
  point), `sync-contributor-docs --check` — all green; empty tree diff across the
  autosquash; each touched position's suite run green. Known edges recorded, not
  fixed: a `consumer-script: false` repo with `package:` entries would fail the
  stamp read loudly (run `uv sync` first) — the only such shape is a python project
  opting out, perverse config; and the generated spine keeps `release-pr-builds`
  for this repo's empty fan (no apps — the verb exits green creating nothing, one
  cheap job per integrate run, the price of fixed topology). Resume at step 36
  (`operator:`): review the rebased branch; the trailing prose commits must NOT be
  dropped at merge — AGENTS.md references the ADR files by name.
- Step 35 landed: the rebase reshaped the whole 90-commit branch — the letter's
  enumeration covered the stage-splicing phases, but the branch also carried the
  lane work they rode — into 16 commits in the guide's five-kind shape on
  `fork-contribution-lane`: agent-doc first, then the code commits (rerun merge
  system, release rework, sync-contributor-docs verb, review anchor, event-keyed
  composites, wheel stamp, jobs schema, splicing, emitting with goldens,
  generator verb with drift checks, lint reduction, ruff design exclusion,
  domain workflow deletions), then the lane/label ADRs with the contributor
  docs as their own prose commit, other-prose last. No prose-deletion commit
  (verified: the branch deletes no prose file that exists on `dev`) and no
  codegen commits (none ran). Backup branch: `fork-contribution-lane-pre-rebase`
  at `6654156`. Verified: empty diff between the tips, matching tree hashes
  (`03fbeb7`), clean status. Green by identity — the tip's tree is the tree
  that was battery green at `04acf76`, with only prose commits after it.
  Resume at step 36 (`operator:`).
- Rebase deviations from the letter: the contributor docs
  (`CONTRIBUTING.md`/`PULL_REQUEST_TEMPLATE.md`) ride the ADR prose commit — the
  letter never placed them, and as gated package data they cannot ride the
  droppable other-prose commit; the four remaining ADRs, the root plans, and
  the todo edits ride other-prose beside `design/stage-splicing/` and
  `adr-certification-by-structure.md`; `ruff.toml`'s design-tier exclusion is
  its own code-side commit (config never rides a prose commit). Excisions, all
  by construction from the cumulative diff: the lint contract layer never
  appears (the base's own contracts delete from their base shape at the lint
  commit; the branch's add-then-delete vanishes), the `save-cache` and
  `head-checkout` composite inputs never appear, the lane-era edits to the
  three domain workflows never appear (their base shapes delete at the
  phase-6 commit), and `preflight.yml` first lands at its phase-2 shape (taken
  from `5748bcc^`) so the dropped input never appears. Lane-era intermediate
  shapes come from `1d50f0a`, the phase-0 tip.
- After the shape rebase, `origin/dev` diverged (npm publish installs the
  committed lockfile before building: `8a773b6`, `91f416f`); the branch was
  rebased onto `91f416f`. One conflict, at the wheel-stamp commit — both sides
  added a constant after `NPM_DEV_DIST_TAG` — resolved keeping both. Battery
  green at the tip (348 tests, ruff, format, basedpyright, lint-workflows all
  clean). This session-state record rides its own prose commit on top; the
  tip's tree is the shape-rebase tree plus dev's npm work plus this file's
  edit.
- Operator rulings recorded before the rebase (it never started — only read-only
  git commands ran): `adr-certification-by-structure.md` is not excised — it
  rides the other-prose commit at the rebase, and this plan rules nothing about
  that commit's fate. Step 35's verification is an empty diff between tips: the
  rebased tree equals the pre-rebase tree exactly.
- The plan was reshaped at the same ruling: the branch goes to operator review
  after the rebase and design may be redesigned there, so the phases past the
  rebase were cut as choreography that presumed an unchallenged landing. Their
  durable content lives in the consumer porting knowledge section below.
- Not verified live, because the sandbox had no `gh` auth and no PR in the org carries a
  review: the review object's fields, the `permission` response, and `gh pr view --json
  author`. They rest on GitHub's documented schemas. The live-validation item in the
  consumer porting knowledge section is the first live check, and a mismatch there is
  fixed in the reads in `merging.py`.
- `list_reviews` parses `gh api --paginate --slurp`, which needs gh 2.40 or newer. The
  gate job runs on `ubuntu-latest`.
- `PullRequest.author` is a nested model after `LabelEntry`, so call sites read
  `pull_request.author.login` rather than the bare string step 4 sketched.

## Verification shorthand

- `battery` (toolkit, in `/workspace/github-actions-toolkit`):
  `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run basedpyright && uv run lint-workflows`
- `battery <consumer>` (in the consumer root):
  `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run basedpyright && uv run pytest`
  (plus the repo extras a step names)
- `toolkit@<sha>`: a clone of `https://github.com/outernet-foundation/github-actions-toolkit`
  at `<sha>` under `/tmp/opencode/toolkit-<sha>`; binding verbs run from it as
  `uv run --project <clone> --locked --no-dev <verb>` with cwd = the consumer root.
- `generate@<sha>`: `toolkit@<sha>` + verb `generate-github-workflows` (add `--check`
  for the drift comparison). Requires the consumer venv synced first (`uv sync --locked`,
  full — domain devkits are dev-group deps whose dist-info the generator reads).
- `T1` = the merged SHA of the toolkit `fork-contribution-lane` landing (step 36).
  `T2` = the merged SHA of the toolkit self-regeneration landing (self-mode
  adoption, whenever it happens). Consumer adoptions pin to the current `T` SHA at
  execution time; consumers re-pin at operator pace.
- `operator:` prefixes a step the executing agent never performs — prepare the request
  (branch, SHA, exact command) and stop.

Sanctioned landing move for unwakeable adoption PRs (the tier-two flip fires neither
trigger): one merge-bot API rebase-merge per repo (`PUT /repos/{org}/{repo}/pulls/{N}/merge`,
`merge_method: rebase`), the standing exception recorded in `adr-fork-contribution-lane.md`.

## Phase 0 — baseline [toolkit]

1. On branch `fork-contribution-lane` (28 commits ahead of `origin`, working tree clean):
   run `battery`. All green before anything changes.

## Phase 1 — the review anchor [toolkit]

Prose first, code second, separate commits.

2. Prose commit: add amendment notes to `adr-fork-contribution-lane.md` (D4 and D5 gain
   the review anchor: the review is the approval — one write-actor review at the payload
   head; the label is the command — the wake and the mode selection; own-PR exemption for
   write-or-above authors) and `adr-ci-label-modes.md` (the label no longer claims to be
   the approval; two deliberate clicks per contributor approval, one for member self-service).
3. Prose commit: rewrite `src/github_actions_toolkit/contributor/CONTRIBUTING.md` —
   approval is "a maintainer reviews your code, then labels it"; the approve button is the
   approval (a green check means vetted, not merged), the `approved-for-*` label commands
   the run; pushing still revokes (strip); red refusal with stripped labels means
   "review at this head, then re-label". `PULL_REQUEST_TEMPLATE.md` only if it repeats
   the old claim.
4. Code commit: `src/github_actions_toolkit/merging.py` —
   - `PullRequest` gains `author: str` (from `PR_VIEW_FIELDS` + `author` in the
     `gh pr view --json` field list);
   - new `ReviewEntry` model: `state`, `commit_id`, `submitted_at`, author login;
   - new `list_reviews(pr_number) -> list[ReviewEntry]` via
     `gh api repos/{GITHUB_REPOSITORY}/pulls/{N}/reviews --paginate`;
   - new `author_permission(author) -> str` via
     `gh api repos/{GITHUB_REPOSITORY}/collaborators/{author}/permission`
     (`.permission` field); a failed call reads as `none` (`bash_check`, no
     exception swallowing); `WRITE_PERMISSIONS = {"admin", "maintain", "write"}`.
5. Code commit: `src/github_actions_toolkit/verbs/gate.py` — the anchor check placed
   after the idle return and after the stacked-pair refusal, before any rebase/mode/marker
   work, on every non-idle wake (including the reuse path):
   - payload head = the checked-out HEAD (`git rev-parse HEAD`);
   - own-PR exemption: `author_permission(pull_request.author)` in `WRITE_PERMISSIONS`
     → skip the review check;
   - else consider only submitted reviews (`PENDING` is not a review) from write actors
     whose `commit_id` equals the payload head; latest by `submitted_at`, ties broken by
     review id (later wins); `APPROVED` passes, anything else (CHANGES_REQUESTED,
     COMMENTED, absence) refuses;
   - refusal: strip every live `approved-for-*` label (existing
     `strip_approval_labels`), post one static teaching comment (review-then-label
     repair instruction, nothing from the PR), exit red;
   - `--dry-run` prints the verdict and the would-strip informationally.
6. Code commit: extend `tests/test_gate.py` — enumerate every verdict case: APPROVED at
   head passes; CHANGES_REQUESTED / COMMENTED / no review at head refuses; review at a
   different `commit_id` counts as absence; PENDING ignored; `submitted_at` tie broken by
   id; non-write reviews ignored in both directions; permission call failure → no
   exemption; own-PR exemption passes without reviews; refusal strips + comments +
   exits non-zero; dry-run informational; the check runs before any git work and on the
   reuse path; the stacked-pair refusal still fires first.
7. Verify: `battery`. Commit boundary: phases 1's commits stand alone.

## Phase 2 — the composites absorb the run's context (OQ3/OQ5/OQ6) [toolkit]

8. `.github/actions/checkout/action.yml`:
   - default `ref` becomes event-keyed: explicit `inputs.ref` always wins; a
     `pull_request` event checks out `github.event.pull_request.head.sha`; everything
     else falls to `format('refs/heads/candidate/{0}', github.event.pull_request.number)`
     — numberless and loud inside git on unsanctioned events, no new guard;
   - add constant `allow-unsafe-pr-checkout: true` on the `actions/checkout` step
     (pinned commit `fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09` already carries the v7
     guard — NO pin bump), with the self-contained rationale comment directly at the
     waiver line (the one sanctioned exception to comment minimality): the guard's scope
     (trusted event + fork PR + fork-head spelling), this fleet's one sanctioned fetch
     (the gate job's payload head), and the mirrored org event policy.
9. `.github/actions/setup-uv/action.yml`: the `save-cache` input dies; the
   `astral-sh/setup-uv` step spells `save-cache: ${{ github.event_name == 'push' }}`
   (the OQ6 sentence's current spelling: pull-request runs restore, push runs save),
   restore always.
10. `.github/actions/release/action.yml`: its inline `astral-sh/setup-uv` step's
    `save-cache: false` becomes `save-cache: ${{ github.event_name == 'push' }}`
    (release runs are push-class → they save).
11. `.github/workflows/preflight.yml` (the reusable): the `head-checkout` input dies;
    the `consumer-script` input stays (typed boolean, default true — the no-Python
    escape); the checkout step's `ref` expression becomes the explicit candidate
    `format('refs/heads/candidate/{0}', github.event.pull_request.number)` (the
    incumbent-`_integrate.yml` call-site fix: a plain-`pull_request` post-gate suite
    keeps certifying the candidate, never the unrebased head); the setup-uv `with:` block
    dies. Note for phase 4: tier-one head checkouts ride the generated inline harness,
    never this reusable.
12. `.github/workflows/mirror.yml`, `.github/workflows/release-pr-builds.yml`,
    `.github/workflows/merge-if-ready.yml`: their `$/.github/actions/checkout` steps
    gain the same explicit candidate `ref` spelling (post-gate files never serve the
    pre-label tier one); their setup-uv `with:` blocks die. `gate.yml` is untouched
    (its explicit `ref: github.event.pull_request.head.sha` wins over the default).
13. Prose commit: `AGENTS.md` — rewrite the install-trio/save-cache/head-checkout prose
    to the event-keyed facts; record the comment-minimality exception (the waiver
    comment at the checkout composite) as codified; drop the identical-`with:` law and
    pair-rule prose where it describes the dead inputs.
14. Verify: `battery` (the lint's lane rules stay keyed-off: this repo's
    `_integrate.yml` remains plain-`pull_request`, so the pair rules are inactive).

## Phase 3 — the universal wheel stamp [toolkit]

15. `src/github_actions_toolkit/publishing.py`: new context manager
    `ephemeral_commit_stamp(package_path, commit_sha)` — writes the file
    `_toolkit_build_commit` (content: the SHA + newline) into the package's source
    directory, discovered from the src layout (the single package directory under
    `<package_path>/src/`; zero or multiple → loud failure); original state restored
    after (delete-or-restore). `PyPIRegistry.publish` runs `uv build` inside both
    `ephemeral_pyproject_patch` and `ephemeral_commit_stamp`; `publish_packages`
    (`src/github_actions_toolkit/verbs/release.py`) threads `settings.github_sha` (the
    minting run's head) through. Universal: every PyPI package the fleet publishes.
    No other registry changes.
16. Extend `tests/test_publishing.py`: the stamp exists inside the window with the SHA
    content, is absent/restored after; a missing or ambiguous `src/` layout fails loudly;
    the stamp file rides the wheel (hatchling packages the whole source directory).
17. Verify: `battery`.

## Phase 4 — the generator [toolkit]

Commit boundaries for this phase are the re-sized list in the session state.

18. `src/github_actions_toolkit/config.py`: `PublishConfig` gains
    - `jobs: dict[str, JobEntry] | None = None` (absent key → the generator self-skips;
      an explicit `jobs: {}` counts as present → generation on, self-mode spine only) and
      a top-level `consumer_script: bool = Field(default=True, alias="consumer-script")`
      (strictyaml string-coerced);
    - `JobEntry` (`extra="forbid"`): exactly one of `package` / `path` / `uses`
      (validator); `repository` required with `package`; optional `file` (stage-file
      path override; default for `package` entries
      `.github/workflows/{key}.yml` in the domain repository, for `path` entries
      `.github/stages/{key}.yml` locally); `runners: list[str] | None`; `secrets:
      dict[str, dict[str, str]]` keyed `pr` / `dev` / `stable`, each map
      slot → repo secret name; `targets: list[str] | None` (subset of
      `integrate`, `release-dev`, `release-stable`; default all three).
19. New `src/github_actions_toolkit/splicing.py` (stage acquisition + transforms):
    - stage document parse: strictyaml-safe load, lift `on.workflow_call`
      (both `on` spellings — YAML 1.1 boolean trap), collect declared `inputs`
      (with defaults) and `secrets` slots;
    - acquisition: `path` entries read locally; `package` entries fetched at the
      stamp over
      `https://raw.githubusercontent.com/{repository}/{pin}/{file_path}`
      (`bash_output` curl); the pin read from the consumer venv's dist-info RECORD
      as a file (`Distribution.discover` over the single
      `.venv/lib/python3*/site-packages`, `distribution.files` entry named
      `_toolkit_build_commit`, `locate().read_text()` — no domain code executes;
      missing stamp / not installed / ambiguous site-packages → loud `SystemExit`);
    - `uses` entries: no fetch — emitted as whole-file reusable calls into the fan;
    - transforms: toolkit `uses:` refs (`outernet-foundation/github-actions-toolkit/…@…`)
      rewritten to the generator SHA (`$/` self-repository spellings in self mode);
      job keys and internal `needs` prefixed `{entry-key}-{job-key}`;
      `inputs.*` references resolved to literals (channel stamped per target file —
      `pr` under integrate, `dev`/`stable` under the release passes — everything else
      from the stage's declared defaults; a referenced input with no declared default
      fails loudly); `secrets.{slot}` references rewritten to the channel's bound repo
      secret (`secrets.{NAME}`), bidirectionally validated — a slot referenced by the
      document with no binding fails, a binding naming an undeclared slot fails;
      `runners` override applied only where the stage's `runs-on` spells the
      `fromJSON(inputs.runs-on)` shape, and only when the stage declares the `runs-on`
      input — else loud failure.
20. New `src/github_actions_toolkit/emitting.py` (the serializer + the fixed spine):
    - byte-stable deterministic output: keys and lists in one stable order; the `on`
      key emitted quoted (`'on':`) so a YAML 1.1 re-read keeps it a string; one
      constant header comment line, no stamps (no generator SHA, no config hash);
      `# zizmor: ignore[dangerous-triggers]` appended to the `'on':` line of each
      lane file (trailing the `'on':` line or on/above the `pull_request_target` line —
      the line above `'on':` is silently ineffective under zizmor 1.30.1); top-level
      `permissions: contents: read` on every generated file; spliced jobs carry the
      permissions their stage declares;
    - fixed spine, never config-expressible:       `gate` (uses the toolkit `gate.yml` at
      the generator SHA, `permissions: contents: write, pull-requests: write`),
      `preflight` (uses the toolkit `preflight.yml` at the generator SHA, needs
      `[gate]`, mode gate, `permissions: contents: read`, and — only when the config's
      `consumer-script` boolean is false — a `with: consumer-script: false` block, the
      one sanctioned `with:` the emitter ever stamps), the mirror slot exactly when
      a `mirror` entry exists (needs `[gate, preflight]`, mode gate), the fan (every
      spliced entry: needs `[gate, preflight]` + the mirror job when present; mode gate
      `needs.gate.outputs.mode == 'full' && (<stage's own if>)` — conjunct, never an
      overwrite; no stage `if` → the bare mode gate), `release-pr-builds` (uses the
      toolkit `release-pr-builds.yml` at the generator SHA, needs `[gate, …fan tails]`,
      `if: ${{ !cancelled() && !failure() && needs.gate.outputs.mode != 'idle' }}`,
      `permissions: contents: write, packages: read`), terminal `merge-if-ready`
      (uses the toolkit `merge-if-ready.yml` at the generator SHA, needs
      `[gate, release-pr-builds]`,
      `if: ${{ !cancelled() && !failure() && (needs.release-pr-builds.result == 'success' || needs.gate.outputs.mode == 'reuse') }}`,
      `permissions: contents: write, pull-requests: read, packages: write`,
      `concurrency: { group: merge, queue: max }`, `with: retry-workflow: retry.yml`,
      `secrets: merge-bot-private-key: ${{ secrets.MERGE_BOT_APP_PRIVATE_KEY }}`);
    - five output files under `.github/workflows/`:
      `integrate.yml` (`pull_request_target: [labeled, synchronize, reopened,
      ready_for_review]` to `dev`; `concurrency: integrate-${{ github.ref }}` with
      `cancel-in-progress: true`), `preflight.yml` (tier one:
      `pull_request: [opened, synchronize]` to `dev`;
      `concurrency: preflight-${{ github.ref }}` with `cancel-in-progress: true`;
      one inline job — `permissions: contents: read`, steps at full toolkit refs at
      the generator SHA: toolkit-checkout, checkout (no `ref` — the event-keyed
      default yields the PR head), setup-uv, `lint-workflows`,
      `validate-release-plan`, `sync-contributor-docs --check`, `uv sync --locked`,
      `generate-github-workflows --check`, and `scripts/preflight.py` stamped only
      when the `consumer-script` boolean is true — the inline spelling is why tier one
      needs no `with:` threading), `release.yml` (push to `main`/`dev`;
      `concurrency: release-${{ github.ref }}` with no cancel; a `build-dev` job
      holding the `release-dev`-targeted fan at channel `dev` with the `dev` secret
      bindings, then the `release` composite `channel: dev` with
      `contents: write, id-token: write, pull-requests: read, packages: read`;
      a `build-main` job holding the `release-stable` fan at channel `stable` with
      the `stable` bindings, then the composite `channel: stable` with
      `packages: write`; fan jobs in release passes carry no mode gate — no gate job
      exists there; workflow-level `env: NUGET_USER: ${{ secrets.NUGET_USER }}` serves
      both delivery jobs — the one sanctioned secret crossing into composite-land), `retry.yml` (`workflow_dispatch` with required `run-id`
      (number), `permissions: actions: write`, one uses: call to the toolkit
      `retry.yml` threading `run-id`), `cleanup-pr-releases.yml`
      (`pull_request_target: [closed]` to `dev`, `permissions: contents: write`,
      one uses: call to the toolkit `cleanup-pr-releases.yml` with
      `pr-number: ${{ github.event.pull_request.number }}`);
    - self mode (detected by the consumer root's origin remote resolving to
      `outernet-foundation/github-actions-toolkit` — local-runnable, no
      `GITHUB_REPOSITORY` dependency): writes the four underscore files
      `_integrate.yml`, `_preflight.yml`, `_retry.yml`, `_cleanup-pr-releases.yml`,
      no `release.yml`; every toolkit ref spelled `$/…` (self-repository, no SHA —
      the fixed-point rule); the merge call threads `retry-workflow: _retry.yml`;
    - the generator SHA is `git rev-parse HEAD` of the clone the verb runs from
      (repo root resolved from `Path(__file__)`).
21. New `src/github_actions_toolkit/verbs/generate_github_workflows.py` — typer app
    (`:app`), `--check` option; write mode regenerates and writes the output files;
    `--check` regenerates in memory and byte-compares against the committed files,
    red with a regenerate instruction on drift. Adoption key: presence of `jobs:` in
    `publish.yml` — absent prints and exits 0. Register in `pyproject.toml`
    `[project.scripts]`: `generate-github-workflows =
    "github_actions_toolkit.verbs.generate_github_workflows:app"`.
22. `.github/workflows/preflight.yml` (the reusable harness): after the
    `sync-contributor-docs --check` step, add `run: uv sync --locked` and
    `run: uv run --project "${{ runner.temp }}/github-actions-toolkit" --locked
    --no-dev generate-github-workflows --check`.
23. `scripts/preflight.py`: after the `sync-contributor-docs --check` self-check line,
    add the same `generate-github-workflows --check` line against the self-test clone
    (`uv run --project "{toolkit_path}" --locked --no-dev
    generate-github-workflows --check`, cwd = this checkout). Inert until the
    toolkit's own adoption (`jobs:` absent → exit 0).
24. Tests (code commit):
    - `tests/test_generate_github_workflows.py` + `tests/test_splicing.py` +
      `tests/test_emitting.py`;
    - golden fixtures under `tests/golden/`: consumer set (`integrate.yml`,
      `preflight.yml`, `release.yml`, `retry.yml`, `cleanup-pr-releases.yml`) and
      self-mode set (`_integrate.yml`, `_preflight.yml`, `_retry.yml`,
      `_cleanup-pr-releases.yml`), asserted byte-for-byte;
    - both secret-typo directions red (stage references an unbound slot; binding names
      an undeclared slot);
    - determinism: two runs produce byte-identical output;
    - config validation: multi-source entry, `package` without `repository`, unknown
      `targets`, unknown channel key — all red;
    - one local zizmor pass (the pinned 1.30.1 binary) over the golden `integrate.yml`
      output asserting the inline `dangerous-triggers` ignore holds and no other
      finding fires on the generated shape.
25. Verify: `battery`. (The toolkit's own `publish.yml` carries no `jobs:` — every
    `--check` self-skips until the toolkit's own adoption.)

## Phase 5 — the lint residue [toolkit]

26. `src/github_actions_toolkit/verbs/lint_workflows.py`: delete the entire contract
    layer — the trigger-keyed wake contracts (`validate_integrate_contract`,
    `validate_preflight_contract`, `validate_cleanup_contract`,
    `validate_retry_dispatch`, `validate_release_concurrency`), the mode-gate checks
    (`validate_reuse_gates`, `validate_merge_gate`), the queue-placement check
    (`validate_merge_concurrency`), the pair rules (`validate_lane_rules`,
    `validate_shared_preflight_call`), the no-secrets scans (`no_secrets_problems`),
    and the SHA law (`collect_pin_problems`,
    `validate_toolkit_pin_consistency`). Keep: the actionlint and zizmor runners with
    their pinned-binary fetch (`ensure_actionlint` / `ensure_zizmor` /
    `ensure_pinned_binary`), and the reusable-shape check
    (`validate_reusable_workflow`) for hand-authored reusables. Found-file scanning
    adds `.github/stages/*.yml` (new `found_stage_files()`; actionlint receives them
    as explicit file arguments; zizmor's repo-root audit input already covers them).
27. `src/github_actions_toolkit/verbs/zizmor.yaml`: reduce to the
    `DO NOT CHANGE THIS FILE WITHOUT EXPLICIT OPERATOR APPROVAL` guard comment plus
    `rules: {}` (the inline ignores in generated files replace the file-level ignores).
28. Prune `tests/test_lint_workflows.py` to the surviving surface plus stage-file
    discovery under `.github/stages/`.
29. Prose commit: `AGENTS.md` — rewrite the `lint-workflows` command row: the runners
    as second opinions over generated output and primary police of hand-authored stage
    bodies and third-party actions; the contract layer is gone because the spelling it
    policed is gone.
30. Verify: `battery`.

## Phase 6 — the domains go home (toolkit side) [toolkit]

31. Delete `.github/workflows/build-unity.yml`,
    `.github/workflows/compile-check-unity.yml`,
    `.github/workflows/build-docker.yml` (they move to the domains at adoption —
    the per-repo facts below).
32. Grep the repo for dangling references (`rg -n "build-unity|compile-check-unity|build-docker"`
    over `src/ tests/ scripts/ .github/`) — verified currently absent from Python;
    fix whatever appears beyond `AGENTS.md`.
33. Prose commit: `AGENTS.md` — remove the build-unity/compile-check-unity/build-docker
    rows from the reusable inventory and the Unity/Docker leg prose they own; the
    leg-schema and shelf-grammar named contracts stay (binding-owned); the Unity YAML
    knowledge moves to the domains.
34. Verify: `battery` — the full battery green at the branch tip.

## Phase 7 — the rebase and the review gate [toolkit]

35. Back up the pre-rebase tip (a branch beside `fork-contribution-lane`), then
    rebase per `/workspace/rebase-style-guide.md` into the five-commit shape: one
    prose-deletion commit (none expected — no prose file existing on `dev` is
    deleted by this branch), one agent-doc commit (every `AGENTS.md`/`CLAUDE.md`
    change from phases 1, 2, 5, 6), the code commits (phases 1–6, excised per the
    guide: the lint contract layer's add-then-delete history, the suffix-flag
    threading, and superseded doc shapes never appear — a change a later change
    replaces lands once, under its final shape), no codegen commits (none ran),
    the ADR amendments as their own prose commit (the phase-1 amendments to
    `adr-fork-contribution-lane.md` and `adr-ci-label-modes.md`), and one
    other-prose commit last (`design/stage-splicing/`: this plan, the samples,
    and `adr-certification-by-structure.md`). The rebased tip's tree equals
    the pre-rebase tree exactly: verify `git diff <old-tip> <new-tip>` is empty
    and the tree hashes match.
36. `operator:` review the rebased branch. Design decisions may be questioned and
    redesigned — this plan presumes no outcome past this point. After review
    clears: push the branch, open the PR to `dev`, satisfy the anchor (the
    operator's own PR rides the own-PR exemption, or review-then-label), apply
    `approved-for-merge`, let the machinery merge. Record `T1` = the merged SHA
    and verify it exists on the remote before any consumer work runs.

## Consumer porting knowledge

Durable knowledge for porting the remaining consumers, decoupled from sequencing
and T-SHAs: each repo's adoption is its own change, executed when the operator
calls for it, pinned to the current `T` SHA at execution time.

### Prerequisite — the org event policy (OQ7)

The org actions-policies allowlist must exist and name a repo before its first
tier-two flip. Ruled values: allowed events `["pull_request_target",
"pull_request"]`; workflow paths `[".github/workflows/integrate.yml",
".github/workflows/cleanup-pr-releases.yml", ".github/workflows/_integrate.yml",
".github/workflows/_cleanup-pr-releases.yml"]`; repository include list
`["github-actions-toolkit", "unity-devkit", "boatyard", "placeframe-capture-tool"]`
(the toolkit first; grows one repo per future adoption); enforcement `active`.
Implementation lives in infra-github-org: a pulumi dynamic resource over
`POST/GET/PUT/DELETE /orgs/{org}/actions/policies` via httpx (no provider
resource exists at the pinned `pulumi-github==6.15.0`) —
`src/components/org_event_policy.py` (`create`/`update` = PUT, `read` = GET,
`delete` = DELETE, id = the org name, `protect=True`), constructed in
`src/stacks/dev.py`; body fields verified against the live endpoint during
implementation, the ruled values above fixed. `operator:` preview + up, then
readback via `gh api /orgs/outernet-foundation/actions/policies`.

### The standing recipe

Per repo:

- (a) an infra-github-org change adding the repo to the policy include list,
  `operator:` preview + up, readback;
- (b) the adoption PR: stage files or `package`/`path`/`uses` entries in
  `publish.yml`, re-pin every toolkit ref in the repo to the current `T` SHA,
  `uv sync --locked`, `generate@T`, `toolkit@T sync-contributor-docs` (write
  mode — the phase-1 canonical lands here), battery, `--check` green;
- (c) `operator:` push, PR, tier one (the generated `preflight.yml`) green on
  the head, then the sanctioned merge-bot rebase-merge — adoption PRs are
  unwakeable (the branch copy declares `pull_request_target`, the default
  branch does not yet), the standing exception recorded in
  `adr-fork-contribution-lane.md`. The merge push fires `release.yml` dev;
- (d) at the first merge push, verify the stamped wheel via its PyPI RECORD:
  `_toolkit_build_commit` present, content = the minting run's head SHA.

The recipe's home is toolkit `AGENTS.md`. Landing it on this branch is a review
decision (step 36).

### Per-repo facts

- **unity-devkit** — work rides branch `channel-identity`; its identity-derivation
  commits are the surviving substance, the branch continues:
  - Verb change: `build_unity.py` reads the keystore quartet from step env
    (`ANDROID_KEYSTORE` base64, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`,
    `ANDROID_KEY_ALIAS_PASSWORD`), decodes the keystore to a runner-temp file,
    and constructs the playerbuild quartet for `player_build`'s env overlay; a
    partial quartet fails loudly. The channel-identity derivation
    (`identity.channel_suffix` in-verb) stays as the branch spells it.
  - Stage files: `.github/workflows/build-unity.yml` and
    `.github/workflows/compile-check-unity.yml`, verbatim from the phase-6
    deletions plus the ruled deltas — every toolkit `uses:` ref spelled full;
    `build-unity.yml` declares `workflow_call` inputs `runs-on` + `channel` and
    secrets: the unity trio (`unity-email`, `unity-password`, `unity-serial`)
    plus the four canonical android slots (`android-keystore`,
    `android-keystore-password`, `android-key-alias`, `android-key-password` —
    exactly one quartet reaches any context via channel-keyed consumer
    bindings); per-job `permissions: contents: read, packages: write` on the
    build/compile legs; the keystore decode step deleted (the verb owns it now).
  - `publish.yml` `jobs:`: `compile-check-unity` via `path:` with
    `file: .github/workflows/compile-check-unity.yml` (a repo cannot stamp its
    own editable install), secrets channel-keyed (the unity trio → `UNITY_EMAIL`
    / `UNITY_PASSWORD` / `UNITY_SERIAL` under every channel).
- **boatyard** — `.github/workflows/build-docker.yml` (with its
  `publish-compose` job) moves from the phase-6 deletion as a hand-authored
  `workflow_call` stage file: full toolkit refs, the getter's score/lock checks
  and the empty-envelope gates verbatim. `publish.yml` `jobs:`: `build-docker`
  via `path:` with `file: .github/workflows/build-docker.yml` (own editable
  install, no stamp). Delete `.github/workflows/merge-gate.yml` (dead
  pre-rerun-lander machinery). Battery plus `uv run boatyard lock --check`.
- **placeframe-capture-tool** (the canary):
  - `pyproject.toml`: delete the `[tool.uv.sources]` `unity-devkit` git source
    (the `unity-devkit>=0.3` dev-group declaration stays; resolves to the
    stamped registry versions).
  - New `.github/actionlint.yaml`: self-hosted runner labels (`self-hosted`,
    `unity`).
  - New `.github/stages/openapi-drift.yml`: hand-authored `workflow_call` stage
    file — toolkit checkout + setup-uv refs, one step `uv run --locked
    openapi-client-codegen --config openapi-client-codegen.yaml --check`.
  - `publish.yml` `jobs:`: `build-unity` via `package: unity-devkit`,
    `repository: outernet-foundation/unity-devkit`, `runners: ["self-hosted",
    "unity"]`, channel-keyed secrets — the unity trio → `UNITY_*` under every
    channel; the canonical android slots → `CI_ANDROID_KEYSTORE` /
    `CI_ANDROID_KEYSTORE_PASSWORD` / `CI_ANDROID_KEY_ALIAS` /
    `CI_ANDROID_KEY_PASSWORD` under `pr` and `dev`, the `ANDROID_*` production
    quartet under `stable`; `build-docker` via `package: boatyard`,
    `repository: outernet-foundation/boatyard`; `mirror` via `uses:` the
    toolkit `mirror.yml`; `openapi-drift` via `path:` (the
    `.github/stages/openapi-drift.yml` default).
  - Generation replaces the hand-authored `integrate.yml`/`preflight.yml`/
    `release.yml`/`retry.yml`/`cleanup-pr-releases.yml`. Battery plus `uv run
    --locked openapi-client-codegen --config openapi-client-codegen.yaml
    --check`. Audit the generated `preflight.yml`: tier one carries no
    `secrets.*` reference anywhere (`github.token` and GitHub-provided env
    exempt).
- **toolkit itself** (self-regeneration): `publish.yml` gains `jobs: {}` — the
  adoption key flips the generator on for the toolkit. Run self-mode generation
  (`uv run --locked --no-dev generate-github-workflows`, cwd = repo root): it
  rewrites `_integrate.yml` (`pull_request_target` wakes `[labeled, synchronize,
  reopened, ready_for_review]` to `dev`), `_preflight.yml`, `_retry.yml`,
  `_cleanup-pr-releases.yml` — `$/` refs, `retry-workflow: _retry.yml` threaded
  on the merge call, no `release.yml` — replacing the hand-authored
  predecessors wholesale; delete any file the generator does not own that the
  old shape left behind. The step-22/23 wiring goes live (the preflight
  harness's sync + `--check` steps and the `scripts/preflight.py` line). The
  org policy already covers the underscore paths (verify the include list still
  names `github-actions-toolkit`). Verify: `battery`, then
  `generate-github-workflows --check` twice with an empty `git diff` between
  and after (byte-stable self-regeneration). `operator:` push, PR (unwakeable —
  branch copy declares `pull_request_target`, default branch does not yet),
  tier-one green on the head, sanctioned merge-bot rebase-merge. Record `T2` =
  the merged SHA; consumers re-pin from `T1` at operator pace, each re-pin PR
  regenerating and re-syncing per the recipe.

### Live validation (first live fork PR — operator-driven, report don't script)

A label without a review reds with the strip + teaching comment;
review-then-label runs the suite bound to the CI quartet only (grep the
generated job env: no `ANDROID_*` production names under the `pr` channel); a
push strips; the prerelease publishes; the merge lands through the terminal.

