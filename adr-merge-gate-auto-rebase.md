# ADR: the merge gate replays onto a side ref and merges the tested replay

Status: accepted — implemented on `adr-merge-gate-auto-rebase` (all questions closed in the
2026-11-18 interview session). This file's v1 (gate force-pushes the PR branch at label time)
was rejected mid-interview for contributor UX; it is preserved as the first entry under
Rejected alternatives.
Execution plan: `plan-merge-gate-certify-ref.md` (linked from here; the plan does not link back).
Date: 2026-11-18.

## Context

The merge gate (`src/github_actions_toolkit/verbs/merge_gate.py`) implements the bors model:
`dev` is evergreen — nothing merges onto it that was not proven green at the exact SHA (and
therefore the exact tree) that merges. Before this design, the human carried the full staleness
burden: the gate refused when `origin/dev` was not an ancestor of the PR head, and the human
rebased locally, pushed, waited for the test suite, then re-poked. The pain is not the typing
— a merge-clean PR still required a manual rebase round-trip before the gate would accept it.

A second pain, equally real and fixed by this design: the `ready-to-merge` label is an event,
not a state. Labeling before green strands the PR — no wake exists at checks-green — so the
docs prescribed remove-and-readd dances for every push, failure, and rebase.

Two hard constraints, unchanged from v1:

1. **Certified-head-is-what-merges.** Four mechanisms are welded to this property: the builds
   shelf is keyed `sha-{full}` at the certified head with the dev-channel release resolving the
   PR head via `commits/{sha}/pulls` (`verbs/release.py`, fetching `refs/pull/{N}/head` at the
   certified SHA); commit-count versioning derives its ordinal at the certified head;    unity
   library cache promotion's premise is the merge's tree-equality with the PR head
   (AGENTS.md, Merging changes); and the evergreen invariant itself — clean textual merges of
   individually-green PRs can combine into a broken tree, and nothing re-validates `dev`.
2. **Semi-linear dev history, always rebase, actual merges disallowed.** PR branches are linear
   runs of rebased commits; the gate's `--no-ff` merge is the only merge commit in
   history; `dev` → `main` is a true fast-forward. Operator ruling, not negotiable.

A third constraint surfaced during the interview: **the label must be state, not event** —
labeling at any time must eventually merge the PR with no re-click ceremonies. In-Actions,
checks-green has no observable event: `workflow_run` is banned (zizmor dangerous-triggers),
and `check_run`/`check_suite` never fire for Actions-created checks
(`todo/supply-chain-control.md`, re-verified against GitHub's docs 2026-11-18: the recursion
guard suppresses both for suites created by GitHub Actions). Any design that waits on the PR's
own checks is therefore poll-bound or dance-bound. The design below neither waits nor polls.
GitHub-decoupling stands as before: plain git + check-runs + one dispatch; only the wake source
and the status query are host-bound.

## Decision

The gate owns a replay side ref. Three dumb wakes feed one idempotent evaluator: the label
event (the human's verb), `synchronize` (any push to the PR), and the replay run's green-gated
terminal step — a run we own needs no doorbell; its last step is our event.

```
wake: labeled | synchronize | replay terminal step
  |
  v
evaluate (idempotent, every wake):
  OPEN? label present? cross-repo? (fork -> refuse loud, Q8)
  |
  v
head test suite (policy C, Q5):
  | green + dev ancestor of head -> merge directly (today's fast path, unchanged)
  | red                          -> refuse loud ("fix, push"); synchronize re-wakes
  | pending OR green-but-stale   -> replay:
  |
  v
rebuild head onto dev tip on refs/heads/merge-gate/{N}
  | conflict -> abort, print conflicted paths; human rebases, pushes (synchronize re-wakes)
  v
force-push side ref (supersedes in-flight replay run via ref-keyed concurrency group)
  |
  v
dispatch consumer integrate on the side ref (pr-number as dispatch input)
  |                                     the run's test suite executes at the replay:
   |                                     the exact history+tree that will merge
  v
terminal step, green only:
  PR head == resolved head? (--force-with-lease carries the SHA; moved -> abort, never clobber)
  dev unmoved?               (moved -> re-rebase loop, max 3, then loud fail + re-poke msg)
  |
  v
sync PR head := tested replay (post-green, the only rewrite of a human branch)
merge --no-ff into dev, push; delete side ref + head branch; sweep pr-{N}-*; promote cache tags
```

Failure reporting: the gate posts a check run on the PR head with the replay's outcome — a
red run posts conclusion failure plus the run link. Replay *progress* is not in-tab (the runs
live on the side ref); the *outcome* is; reproducing a red replay in-tab is a local
rebase-and-push away.

No cron. The wake set is complete assuming no platform flaps; a lost wake is repaired by the
same human move as before (re-apply the label). A slow scheduled sweep is the sanctioned future
hardening when lost wakes become real — it must never be load-bearing for happy-path
correctness.

Properties:

- Dev history keeps its shape: replayed PR commits on a dev tip, one gate merge per merged PR.
  The label-time and failure-time behavior toward human branches is *better* than v1: nothing
  is ever rewritten pre-green.
- The evergreen invariant holds at full granularity, and the merged
  tree was proven by a full
  integrate run at the exact replay that merges.
- The head sync at merge time makes the PR head the certified SHA, so GitHub closes the
  PR as **Merged** and all four welds hold unmodified: release resolves the synced head, the
  shelf keys `sha-{H'}` from the replay run's head, counts derive at that head, promotion's
  tree equality holds.
- Label-as-state: one click, whenever. The red-test-suite recovery loop is "fix, push" — no
  re-label, no dance.
- The terminal step runs inside the consumer's own replay workflow with the merge-bot secret
  forwarded — the same trust boundary as the gate call (the consumer's CI can already merge
  its own repo).

## Rejected alternatives

- **Gate rebases the PR branch in place (this ADR's v1).** Force-push the rebased head at
  label time; integrate re-runs on `synchronize`; merge. All welds survive and the mechanics
  are minimal, but a red run leaves the contributor facing a rewritten remote and a diverged
  local — recovery is a `git pull --rebase` you have to know about. Rejected: the failure path
  must never rewrite a human branch. The side-ref design keeps the v1 weld analysis (the sync
  merges the same SHAs) while making the failure path pure.
- **Merge the rebased head without a replay run.** Deletes the replay cycle, breaks the
  evergreen invariant, silently ships stale shelf artifacts, rots promotion, drifts counts.
  No cheap coherent version exists.
- **Merge `dev` into the head at label time.** Plants merge commits into dev's reachable
  history — violates the semi-linear ruling (operator, design session).
- **Run on `refs/pull/N/merge`.** Recomputed under you on base movement, silent fallback to
  head on conflict; deep GitHub coupling.
- **GitHub native merge queue.** Maximal GitHub coupling with a CI port planned; and the queue
  merges merge-group trees — it cannot express head-identity certification
  (`todo/supply-chain-control.md`).
- **Classic bors merge-commit shape** (test the head-into-dev merge, merge that commit).
  Preserves signatures and review anchors verbatim; merges diamonds onto dev — violates the
  semi-linear ruling. Recorded as the standing escape hatch if signature enforcement or
  review-anchor pain ever outweighs semi-linearity (see Q7).
- **Cron sweep as a primary wake / gate polling the side ref.** A cron is a poll that hacks
  around missing events; here no event is missing. Demoted to future flap-repair only.
- **`check_run`/`check_suite` as the checks-green wake.** Platform-dead: the recursion guard
  suppresses both for Actions-created checks (field reports corroborate). GitHub App webhooks
  *do* receive them (bors-ng lineage) — the external-service door if this is ever needed.
- **`workflow_run`.** Banned outright (zizmor dangerous-triggers; AGENTS.md workflow contract).

## Accepted costs

1. One extra full integrate run per stale merge — irreducible under certified-tree-merges;
   every correct design (including GitHub's queue) pays it.
2. Label-while-pending burns a redundant head test suite alongside the replay run (policy C's
   price for killing the dance; the head run is the contributor's in-tab feedback).
3. Replay progress is invisible in the PR checks tab; only the outcome arrives there.
4. New push surface for the merge-bot App: force-push on unprotected refs — the side ref
   freely, a PR head exactly once per merge, post-green only (Q3 checklist covers
   verification).
5. Review anchors go outdated at the merge-time sync — posthumous (the PR closes as Merged a
   second later), and strictly milder than the status quo, where a post-review rebase
   outdates them mid-flight with re-approval ceremony.
6. The CI-commit-free invariant gains an ephemeral-refs clause (Q2).
7. Unsigned-fleet precondition (Q7): any repo that later enforces commit signatures or DCO
   cannot adopt this gate.

## Closed questions

- [x] **Q1 — merge wake: re-poke, poll, or callback.** Decision: three wakes — `labeled`,
  `synchronize`, and the replay run's green-gated terminal step. No cron now; the human
  re-poke is the interim flap repair; a slow scheduled sweep is sanctioned later solely as
  flap repair, never load-bearing. Rationale: the label is state; green-detection in-Actions
  is `workflow_run`-or-nothing (verified: recursion guard suppresses `check_run`/`check_suite`
  for Actions-created checks); owning the replay run makes its terminal step the green event;
  `synchronize` covers every human push. The per-PR `merge-gate-{N}` concurrency group
  serializes evaluator wakes; the terminal step lives in the replay workflow and is serialized
  by nothing — the lease check (Q3/Q4) is the backstop.
- [x] **Q2 — CI-commit-free invariant wording.** Decision: split in two. Protected branches:
   unchanged text — the merge remains the only commit CI creates on `dev`/`main`, and
  `dev` → `main` stays a true fast-forward. Ephemeral refs, new clause: the gate owns
  `merge-gate/{N}` — created, force-updated, deleted at will, no ruleset, no history value —
   and CI rewrites a PR head exactly once per merge, post-green, as the sync to the tested
  replay; human branches are otherwise never touched.
- [x] **Q3 — push surface and lease semantics.** Decision: the merge-time head sync pushes
  `--force-with-lease` pinned to the exact head SHA resolved at cycle start — a concurrent
  human push aborts loudly instead of being clobbered; the abort message is the standing
  re-poke instruction. The side ref is force-pushed freely (gate-owned). The dev push is
  unchanged (App token, `evergreen-dev` ruleset bypass). Operator checklist, folded into the
  Q6 dogfood: verify the App's Contents:write covers branch create/force-push on unprotected
  refs, and that PR branches and `merge-gate/*` are not covered by any ruleset forbidding
  force-push.
- [x] **Q4 — race-loop bound and mid-cycle push detection.** Decision: max 3 re-rebases per
   merge attempt, then fail loud with the re-poke message. Mid-cycle human push: the
  `synchronize` wake starts a fresh cycle whose side-ref force-push auto-cancels the in-flight
  replay run (the consumer's integrate already runs `integrate-${{ github.ref }}` with
   cancel-in-progress, so the ref-keyed group does the superseding); a push inside the merge
   window trips the lease and aborts the merge — never a clobber, never a stall, at most one
   wasted test suite. The push-during-merge race with a synchronize-woken evaluator is not
  serialized by `merge-gate-{N}` (different workflows) — the lease is the last line.
- [x] **Q5 — test-suite preconditions (policy C).** Green at label + rebased → merge directly,
  no dispatch. Green + stale → replay (the necessary run). Pending at label → dispatch the
  replay immediately; the head's own run finishes in parallel as redundant in-tab feedback
  (accepted burn; people who wait-for-green pay nothing). Red at label → refuse loud with
  "fix, push". Head-green-before-rebase is no longer a precondition — wake completeness forced
  the drop, since waiting on the PR's checks means waiting on a doorbell that does not exist.
  The recursion question dissolves: the terminal step queries no check runs (the enclosing
  run's success is the outcome); the fast path's test-suite query and `GATE_CHECK_NAME`
  self-exclusion are unchanged; a synchronize-triggered gate wake is impossible today (wake
  is `labeled` only) and the consumer contract change below adds `synchronize` deliberately —
  the evaluator's label-presence filter is the guard.
- [x] **Q6 — dogfood.** Decision: **placeframe-capture-tool** — the canonical full-suite
  consumer (mirror → preflight → build-unity → release-pr-builds). Live checklist, end to
  end: dispatch fires integrate on the side ref with the pr-number input; ref-keyed
   concurrency supersedes an in-flight replay run; the terminal step merges; head sync shows
  the PR as Merged; the failure check run appears on the PR head; `pr-{N}-{count}` is cut
  from the replay run; the dev release resolves the synced head and pulls shelf `sha-{H'}`;
   commit count derives at `H'`; unity cache promotion arrives on the dev tag; branch, side-ref,
  and release sweeps run; the fork refusal fires (the repo holds the fleet's one historical
   fork PR); the App's force-push surface and ruleset coverage behave (Q3 items). This repo
   cannot dogfood (operator-direct merging, ruling 2026-10-11). A cheap first shake-out on a
  tiny suite (bashrun) before burning a unity leg is optional, not required.
- [x] **Q7 — signatures and authorship.** Survey run 2026-11-18: no fleet repo enforces
  signatures or DCO; stray individually-signed commits only. Decision: record the
  unsigned-fleet assumption as an adoption precondition of this gate. Note the status quo
  breaks signatures identically (any human rebase rewrites commits); this design adds no new
   breakage. Escape hatch for a future signing repo: classic-bors merging (see Rejected
   alternatives) or manual merging.
- [x] **Q8 — fork PRs.** Survey run 2026-11-18: among the 13 gate consumers, exactly one true
  fork PR ever (placeframe-capture-tool, from a contributor fork); the fork-heavy repo
  (placeframe) runs no gate. Decision: the gate refuses cross-repository PRs loudly ("fork
   PRs must be rebased and merged manually"). Dual motivation: dispatching a replay run on a
  ref containing fork code would run untrusted content in a trusted, secret-bearing context
  (the `pull_request_target` shape — this rule is a hard security boundary, not a Q8
  footnote), and the bot could not sync a fork's head anyway.
