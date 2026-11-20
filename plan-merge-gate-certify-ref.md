# Plan: merge-gate replay side ref — evaluate/merge verbs, fleet migration

Status: the execution plan for the accepted side-ref replay design; implemented on
`adr-merge-gate-auto-rebase`. All design questions were closed in the 2026-11-18 interview
session; the ADR records them. Consumers are untouched — migration rides this plan.

## Context

The human carried the full staleness burden before this design: the gate refused any PR whose
head was not rebased onto `dev`, so a merge-clean PR still needed a manual rebase round-trip.
Worse, the label was an event, not a state — labeling before green stranded the PR, and the
docs prescribed remove-and-readd dances for every push, failure, and rebase. In-Actions,
checks-green has no observable event (`workflow_run` banned; the recursion guard suppresses
`check_run`/`check_suite` for Actions-created checks), so the design neither waits nor polls:
the gate rebuilds the PR head onto the dev tip on a side ref it owns, runs the consumer's own
integrate test suite on that replay, and merges the tested replay — syncing the PR head
post-green so the PR closes as Merged and the four certified-head welds (shelf keying,
release head resolution, commit-count ordinals, promotion tree equality) hold unmodified.

## Verb mechanics

Two console scripts over one shared `gate` module (`src/github_actions_toolkit/gate.py`: the
PR model, side-ref grammar, replay, dispatch, and the merge-into-dev sequence). The
consumer-side spelling is law (stable-CLI-API; matches the AGENTS.md Commands rows).

**Evaluate** — `merge-gate [--dry-run]`, its PR number parsed from the ambient `GITHUB_REF`
(`refs/pull/{N}/merge`), woken by `labeled` and `synchronize`:

1. Resolve the PR (`git branch -r --contains`, then `gh pr list --head … --base dev`,
   then `gh pr view` for state, head, labels, cross-repo flag).
2. Label absent → clean no-op, exit 0. State not OPEN or **cross-repository → refuse loud**
   ("fork PRs must be rebased and merged manually") — the hard security boundary: a replay
   dispatch on a ref containing fork code would run untrusted content in a trusted,
   secret-bearing context.
3. Head test suite (check-runs query; the exclusion matcher drops the gate's own in-progress
   check and the `merge-gate replay` check): any completed non-green → refuse loud
   ("fix, push" — `synchronize` re-wakes on the fix push). All green AND `origin/dev` is an
   ancestor of the head → merge directly, the fast path. Pending OR green-but-stale → replay.
4. Replay: `fetch origin refs/heads/dev`, detach at the head SHA, rebuild
   (`git rebase --onto FETCH_HEAD <merge-base> <head>`); on conflict, abort, print the
   conflicted paths (`git diff --name-only --diff-filter=U`), exit loud — the human rebases
   and pushes. Green path: force-push `+HEAD:refs/heads/merge-gate/{N}` (the App token's
   credential helper, the `GIT_COMMAND` pattern), then
   `gh workflow run integrate.yml --repo {repo} --ref refs/heads/merge-gate/{N}`
   with `-f pr-head-sha={H} -f attempt=1` — the replay run.

**Merge** — `merge --pr-head-sha <sha> [--attempt <n>] [--dry-run]`, its PR number parsed
from the ambient `GITHUB_REF` (`refs/heads/merge-gate/{N}`);
`TEST_SUITE_RESULT` rides step env (values `success|failure|cancelled|skipped`):

1. `TEST_SUITE_RESULT != success` → post the failure check run on `pr-head-sha`: name
   `merge-gate replay`, conclusion `failure`, details_url from the ambient
   `GITHUB_SERVER_URL`/`GITHUB_REPOSITORY`/`GITHUB_RUN_ID`; exit nonzero. Auth:
   `JOB_GITHUB_TOKEN` (the job's `GITHUB_TOKEN` under `checks: write` — the minted App token
   holds checks:read only). Success posts nothing — the PR closes as Merged a second later.
2. Suite green: re-resolve the PR; re-assert OPEN and label present (label removal while the
   replay ran = withdrawn intent → abort loud). `headRefOid != pr-head-sha` → abort loud with
   the standing re-poke message (soft pre-check; the lease push is the hard one).
3. `fetch origin refs/heads/dev`; dev tip not an ancestor of the side ref's checkout → dev
   moved: re-rebase the replay's commits onto the fetched tip (the commits are side-ref HEAD
   minus its old dev base), force-push the side ref, re-dispatch with `attempt+1`, exit 0.
   `attempt > 3` → loud fail with the re-poke message.
4. Unmoved: sync the PR head to the tested replay with
   `--force-with-lease=refs/heads/{headRefName}:{pr-head-sha}` — a concurrent human push
   fails the push and aborts loudly, never clobbers.
5. Merge: `--no-ff` into `dev` and push (App-token + evergreen-dev bypass path, unchanged),
   delete the side ref and the head branch, `delete_releases_by_prefix("pr-{N}-")`,
   `promote_scope` — the shared `gate` helpers.

`--dry-run` on both verbs exercises the read path against live GitHub with zero side effects
and prints one plain sentence naming the branch that would fire. `scripts/preflight.py`
self-test runs both dry-runs (`merge-gate --dry-run` and
`merge --pr-head-sha {head} --dry-run` with `TEST_SUITE_RESULT=success`, both resolving the
PR number from the run's ambient `GITHUB_REF`)
against a clone of this repo at the workspace HEAD.

## Side-ref lifecycle

`refs/heads/merge-gate/{N}`: created/force-updated by evaluate; superseded by the next replay
(the dispatch shares the consumer's `integrate-${{ github.ref }}` concurrency with
cancel-in-progress — a re-dispatch on the side ref auto-cancels the in-flight run; zero
consumer concurrency changes); deleted by merge after the dev push; swept on PR close by
`cleanup-pr-releases`, which carries an idempotent branch deletion
(`DELETE repos/{repo}/git/refs/heads/merge-gate/{N}`, absent ref a no-op, `GITHUB_TOKEN`
under the call's existing `contents: write`). No ruleset covers the ref, ever.

## Workflow surface (this repo)

- `merge-gate.yml` (reusable): the mint step adds `permission-actions: write` (dispatch).
  Nothing else changes.
- `merge.yml` (reusable, `workflow_call` only, no top-level concurrency): inputs
  `pr-head-sha` (string, required), `attempt` (number, default 1),
  `test-suite-result` (string, required); secrets `merge-bot-private-key` (required);
  `permissions: {contents: read, packages: write, checks: write}`; steps toolkit-checkout →
  consumer-checkout (`ref: github.sha`, `fetch-depth: 0`, tags-less) → setup-uv →
  create-github-app-token (contents write, pull-requests read, checks read, actions write) →
  the merge verb with step env `PR_NUMBER`/`PR_HEAD_SHA`/`ATTEMPT`/`TEST_SUITE_RESULT`,
  minted `GITHUB_TOKEN`, `JOB_GITHUB_TOKEN`, and the `REGISTRY_*` trio (promotion, same as
  merge-gate.yml). `PYTHONUNBUFFERED` top-level.
- `release-pr-builds.yml`: job gate widens to
  `if: github.event.pull_request || github.event_name == 'workflow_dispatch'`; the
  consumer-checkout ref gains the fallback (`github.event.pull_request.head.sha ||
  github.sha`).
- `release.py`: the pr-channel PR-number parse accepts `refs/heads/merge-gate/{N}`
  alongside `refs/pull/{N}/merge` — the replay run cuts the `pr-{N}-{count}` release at
  the replay, which is what merges.
- `lint_workflows.py`: wake contract is `types: [labeled, synchronize]` (branches `[dev]`,
  same group, no cancel); the `integrate.yml` contract requires `workflow_dispatch` with
  required inputs `pr-head-sha` (string) and `attempt` (number) — the replay dispatch
   entry. This repo's own `integrate.yml` carries the inputs inertly (self-lint; it arrives
   operator-direct, never dispatched, no merge job).

## Consumer migration surface

Per repo, ONE commit (atomic cutover — the new lint reds a half-migrated file): wake types
become `[labeled, synchronize]`; `integrate.yml` gains the dispatch inputs (`pr-head-sha`
string required, `attempt` number required) and the terminal
merge job; every `uses:` repins to the new toolkit SHA (one SHA repo-wide). The merge job,
verbatim (job key order per the contract):

```yaml
  merge:
    needs: [release-pr-builds]
    if: ${{ !cancelled() && github.event_name == 'workflow_dispatch' }}
    permissions:
      contents: read
      packages: write
      checks: write
    uses: outernet-foundation/github-actions-toolkit/.github/workflows/merge.yml@<sha>
    with:
      pr-head-sha: ${{ inputs.pr-head-sha }}
      attempt: ${{ inputs.attempt }}
      test-suite-result: ${{ needs.release-pr-builds.result }}
    secrets:
      merge-bot-private-key: ${{ secrets.MERGE_BOT_APP_PRIVATE_KEY }}
```

`!cancelled()` is load-bearing: a red suite must still reach the merge call so the failure
check run reaches the PR head. `release-pr-builds` is the terminal fan-in in every consumer's
integrate (verified fleet-wide).

Roster (surveyed 2026-11-18 against remotes): **13 active gates** — Make-it-Sing, bashrun,
boatyard, build-artifact-registry, infra-rathole, lbe-toolkit, logger-conf,
openapi-client-codegen, placeframe, placeframe-capture-tool, pydantic-settings-pulumi,
python-devkit, unity-devkit — plus **Nessle and ObserveThing** (gate file on `dev` only,
never promoted, workflow unregistered) and **StatefulUnity** (fofxland org, App not installed
there — unverifiable via the sandbox token; local checkout carries the gate). Pin spread at
survey: `c6221cf` ×9, `f2d576a` ×4, `825088c` (Make-it-Sing), `47e2945` (unity-devkit).
Placeframe's gate is active on disk but operationally dormant ("runs no gate") — migrate its
files anyway; uniformity is the point.

## Operator prerequisites (before the first replay dispatch)

- merge-bot App gains **Actions: write** (workflow dispatch) with installation
  re-authorization. Everything else it needs it already holds (Contents: write for branch
  create/force-push on unprotected refs; Pull-requests/Checks: read).
- Ruleset audit (Q3 checklist): no ruleset covers PR head branches or `merge-gate/*`; the
  `evergreen-dev` Integration bypass is unchanged; dev push path untouched.
- Toolkit merge to the remote (operator push) before any consumer repin — the pinned SHA
   must exist before consumer CI runs.

## Ordering constraints

1. This repo: implementation branch off `dev`; prose commits separate from code; operator
   push delivers it.
2. Dogfood: **placeframe-capture-tool** migrates first — its migration PR is the first PR to
   merge through the new gate (meta, exact: the gate merges its own adoption). A bashrun
   shake-out on the tiny suite first is optional, not required.
3. Fleet sweep: remaining consumers, one repo = one PR merge via its own gate.
4. Local consumer checkouts lag remotes — the operator pulls before each is touched.

## Verification (Q6 dogfood checklist, live, end to end — placeframe-capture-tool)

- Dispatch fires integrate on the side ref with the pr-head-sha and attempt inputs.
- Ref-keyed concurrency supersedes an in-flight replay run.
- The terminal step merges; the head sync shows the PR as Merged.
- The failure check run appears on the PR head.
- `pr-{N}-{count}` is cut from the replay run.
- The dev release resolves the synced head and pulls shelf `sha-{H'}`.
- Commit count derives at `H'`.
- Unity cache promotion arrives on the dev tag.
- Branch, side-ref, and release sweeps run.
- The fork refusal fires (the repo holds the fleet's one historical fork PR).
- The App's force-push surface and ruleset coverage behave (Q3 items).
- This repo cannot dogfood its own gate (operator-direct merging, ruling 2026-10-11); its
  preflight self-test exercises both dry-run modes instead.

## Current state

- github-actions-toolkit: branch `adr-merge-gate-auto-rebase` = origin/dev (`f2d576a`) + the
  AGENTS.md spec-first amendment + this ADR and plan + the implementation (evaluate and merge
  verbs, `gate` module, `merge.yml` reusable, lint contracts, self-test).
- Consumers untouched; pin spread as surveyed above.
- Sandbox notes: reads via `GH_TOKEN=$(uv run --project /pulsar/scripts mint-github-app-token)`;
  no pushes (the App token is read/PR-write only — hand branch + SHA to the operator);
  never `gh run watch`.
