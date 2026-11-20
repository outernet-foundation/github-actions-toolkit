# ADR: one merge workflow — integrate rebases, tests, and merges; retries are re-runs of the PR-associated run

Status: accepted — design converged in the 2026-11-19 interview session; implemented. Supersedes
the evaluator half of `adr-merge-gate-auto-rebase.md` (the gate verb, the dispatch replay entry, the fast
path); that ADR's merge semantics stand unchanged (side ref, terminal merge, certified-head welds, the
evergreen ruleset). The merge tail described here (head sync, local `--no-ff` merge) is superseded by
`adr-api-rebase-merge-landing.md`; the rerun/retry halves stand. PR identity resolves from the ambient
`GITHUB_REF` (`pull_request_number_from_ref`
in `refs.py`, both ref spellings).
Date: 2026-11-19.

## Context

The v1 design (`adr-merge-gate-auto-rebase.md`) kept a separate evaluator — the `merge-gate` verb — that
photographed the checks tab, preserved the pre-ADR fast path (the gate merges green-and-rebased heads
directly), and manufactured replay runs by dispatching integrate on the side ref. Three defects surfaced
under examination:

1. **The fast path forks merge authority.** `merge-gate` merges on one branch, `merge` merges on the
   other. The fast path's certificate is a point-in-time read — a photograph — with a read-to-push race
   window: the suite can turn red after the read (flaky re-run, straggler check) and the head can move,
   and nothing downstream catches either, because the lease lives only in the replay terminal. Merging
   on a photograph is the one act this architecture exists to prevent; the fast path was its sole
   remaining instance.
2. **The dispatch entry is PR-blind.** Documented rule: checks created by workflow *jobs* count for a
   pull request only when the run is triggered by `push`, `pull_request`, `pull_request_review`,
   `pull_request_target`, `deployment`, or `deployment_status` — a `workflow_dispatch` run on the side
   ref carries no PR association and never renders in the PR's checks tab
   (docs.github.com, *Troubleshooting required status checks*). Retry attempts were invisible on the PR
   page, the exact surface humans need.
3. **Every labeled push burned two suites** — the in-tab run and the dispatched replay — testing
   near-identical trees.

The interview's structural conclusions: "replay" was never a distinct object — every run can be a
candidate merge; the gate's residual job (deciding when to enter the loop) is unnecessary once every
run is an entry; and the only certificate worth holding is a run this system owns at the exact tree that
merges.

Platform facts this design rests on (verified against GitHub docs, the gh CLI source, live API traces,
and production precedents):

- **Re-runs of a `pull_request`-triggered run replay the frozen original event payload** — same
  `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT` incremented, same `GITHUB_SHA`/`GITHUB_REF`/`github.event` —
  and stay fully PR-associated: native checks-tab entries, in-progress spinners, per-attempt logs
  (`…/runs/{id}/attempts/{n}`), latest attempt winning per check name
  (docs.github.com, *Re-running workflows and jobs*).
- **The rerun API only works on completed runs** — a run re-requesting itself mid-flight gets
  `403 "This workflow is already running"` (cli/cli#9221, apache/tvm#12847).
- **`workflow_dispatch` and `repository_dispatch` are exempt from the `GITHUB_TOKEN` recursion guard** —
  a run may always dispatch another workflow (docs.github.com, *Triggering a workflow*).
- **Limits:** 50 re-runs per run (2026-04 changelog; fresh budget per run, and each push mints a fresh
  run), a 30-day window, full re-execution of all jobs per attempt, the original workflow file version,
  and the original triggering actor's privileges.
- **Frozen payload corollary:** `github.event.pull_request.head.sha` does not update on later attempts —
  freshness checks must read live state, never the payload.

## Decision

One workflow, one loop, one merge authority. The consumer's `integrate.yml` is the whole merge machinery; the
gate ceases to exist as a concept.

```
wake: pull_request [opened, synchronize, reopened, labeled] to dev   |   retry (rerun of this run)
  |
  v
rebase job (toolkit `rebase` reusable + verb):
  PR number from ambient GITHUB_REF; fork PR -> pass the plain head through
  rebase the (frozen-payload) head onto the CURRENT dev tip
    conflict -> abort with the conflicted paths; human rebases, pushes (synchronize re-wakes)
  force-push refs/heads/merge-gate/{N}                      <- the rebase's home; unchanged physics
  |
  v
test jobs (mirror -> preflight -> build legs -> release-pr-builds), unchanged composition;
  each checks out the side ref, resolved ambiently (checkout runs the candidate-ref verb)
  |
  v
terminal merge job (success-gated: red attempts render natively in the PR checks tab and never
  reach the verb):
  fork PR          -> refuse "fork merges are currently unsupported"
  label withdrawn  -> quiet exit 0 (unlabeled WIP runs must stay green)
  PR head moved    -> abort loud (lease: live gh pr view vs the frozen payload head)
  dev moved        -> gh workflow run retry.yml -f run-id={GITHUB_RUN_ID}; exit green
  attempt bound    -> GITHUB_RUN_ATTEMPT > 3 -> loud re-poke, no retry dispatched
  all quiet        -> merge: --force-with-lease head sync (lease pinned at the payload head),
                      merge --no-ff into dev, delete side ref + head branch,
                      sweep pr-{N}-*, promote the cache

retry.yml (thin consumer shim: workflow_dispatch + run-id; lint-mandated)
  -> toolkit `retry` reusable -> `retry` verb:
       poll GET /actions/runs/{id} until completed (seconds), POST /runs/{id}/rerun, exit
  -> attempt N+1 of the SAME run: PR-associated, checks tab native,
     rebase job re-rebases the frozen head onto the new dev tip
```

Elements and their laws:

- **The run is the certificate.** Nothing merges on a read. The checks tab is demoted from evidence to
  convenience; nothing machine-reads it, and the `evergreen-dev` ruleset (merge-bot bypass only) keeps
  humans from acting on it.
- **The candidate ref is ambient.** `checkout` resolves `refs/heads/merge-gate/{N}` through
  the `candidate-ref` verb, parsing `GITHUB_REF` (both spellings); one fallback (side ref absent ->
  the event head) covers the fork pass-through. No `ref` threading anywhere: no job outputs, no
  required inputs, no fallback chains downstream of the rebase job.
- **The batons die.** `pr-head-sha` is the frozen payload head on every attempt; the attempt counter is
  the ambient `GITHUB_RUN_ATTEMPT`; the retry dispatch carries only `run-id`. `test-suite-result` dies
  too: the terminal is success-gated (red attempts render natively in the PR checks tab and never
  reach the verb), so nothing about the suite needs threading across the `uses:` wall.
- **The merge verb's dev-moved branch loses the rebase.** Attempt N+1's own rebase job re-rebases; the
  terminal's retry path collapses to "dispatch retry, exit green."
- **Dispatch addresses files; `uses:` addresses reusables.** Every dispatch target is a thin consumer
  shim plus a toolkit reusable — `retry.yml` is the one new consumer file; the rerun call needs
  `actions: write` on the consumer's repo, and the consumer run's own context is the natural holder of
  that grant.
- **Vocabulary:** `rebase` (job/reusable/verb) and `retry` (shim/reusable/verb). The word "replay" dies
  with the concept — there was never a separate thing called a replay, only runs and their attempts.
- **Unlabeled pushes** run the suite (the status quo's own cost), rebase, and push a side ref nobody
  consumes; the existing closed-PR sweep deletes it. No label gate exists upstream of the terminal.

## Rejected alternatives

- **Keep the fast path** (gate merges green-and-rebased directly). The photograph sin; forks merge
  authority; the head-race and suite-snapshot holes have no backstop on that branch. Deleted.
- **Dispatch-entry retries** (v1's replay). PR-blind attempts; the manual check-run stitch that patches
  them (the microsoft/FluidFramework and home-assistant/android pattern) is cosmetic — arbitrary
  check-suite grouping, `details_url` rewriting in PR-context suites — and is retained only as the
  documented fallback should the rerun path ever be blocked (50-cap exhaustion, the
  "cannot be retried" ineligible classes).
- **Commit-status stitch** (what bors-ng and homu actually do): renders in the merge box, not the
  checks tab; no in-progress state — why classic bors UIs are a single bubble.
- **Self-rerequest mid-run:** 403, verified dead.
- **Label-cycling for machine re-entry** (`pull_request[labeled]` re-fire): `GITHUB_TOKEN`-added labels
  are inert under the recursion guard; needs an App/PAT; timeline noise; new `run_id` per attempt.
- **Native merge queue:** merge groups are first-party-only (no creation API). Noted as the maintained
  productization of this entire system, should the org ever adopt it.
- **Rebasing the PR branch in place:** rewrites human branches pre-green — v0's rejection, unchanged.
- **Intra-run loops over the test jobs:** runs are one-pass DAGs; no such primitive exists. The loop is
  a chain of attempts of one run.

## Accepted costs

1. **Every merge pays one full suite**, including green-and-rebased quiet PRs (the fast path's former
   domain): minutes instead of seconds. Against v1 the arithmetic improves: one run per labeled push
   instead of two.
2. **One full re-execution per retry** (reruns re-run succeeded jobs too) — the same per-retry cost as
   v1's dispatch replay.
3. **Contention:** every merge preempts in-flight attempts elsewhere. The retry herd is a
   self-draining queue — each round merges at least one, so it always terminates once pushes stop; it is
   not a deadlock or a livelock, but it is O(N²) runner-time under load. The max-3 bound plus re-poke
   hands timing back to humans rather than spending unboundedly on a contested minute.
4. **The placement quirk:** the PR checks tab pins a run's marks to the payload head while the tested
   tree is the rebased candidate — off by one rebase whenever dev had moved. Cosmetic: the logs are
   real, the click-through is real, nothing machine-reads the marks, and the ruleset blocks human
   merges.
5. **Rerun limits:** 50 attempts per run (fresh budget per push), 30-day window, original triggering
   actor's privileges (fork attempts behave like their attempt 1 — the pass-through covers them).
6. **A seconds-long relay gap** between attempt N's terminal and attempt N+1's start (the retry shim's
   poll for run completion).
7. **Lost-wake surface:** a failed retry dispatch leaves a green-but-unmerged labeled PR; the standing
   human repair (re-apply the label) covers it, as it does every other lost wake in this design.
