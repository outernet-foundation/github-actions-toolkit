# ADR: the readiness-label ontology — as-is by default, rebase as the called-out case

Status: accepted — implemented on `adr-merge-gate-auto-rebase` (operator rulings of 2026-11-20:
the CI-label posture, the as-is default, and the final vocabulary). Builds on
`adr-tested-marker-reuse.md` (the mode output subsumes that ADR's `reuse` flag); the wake-set
amendment below modifies `adr-integrate-rerun-lander.md`.
Date: 2026-11-20.

## Context

Two sharp edges in the four-wake rerun machinery:

1. **Every wake is a full run.** `opened` and `synchronize` fire regardless of intent, and no
   gate exists upstream of the terminal — a WIP push burns a full suite (unity legs, docker
   legs, mirror). People may open a PR and not want CI at all yet.
2. **Exactly one mode exists: rebase-onto-dev-or-die.** A deliberately diverged branch — known
   conflicts, CI on the branch as it stands wanted for its own sake — cannot use the machinery
   at all: the rebase job aborts red on conflict, and silent fallback to the unrebased head was
   already rejected doctrine (the `refs/pull/N/merge` rejection in
   `adr-merge-gate-auto-rebase.md`).

Platform fact, verified 2026-11-20: GitHub labels have no exclusivity, grouping, or value
semantics (community discussion #16682, open for years). The only native single-select is the
Projects v2 field, which cannot wake a run. So contradiction is expressible and must be
*refused loudly*, not made unexpressible; bot-enforced label exclusivity is deferred as future
hardening (GITHUB_TOKEN label writes are inert under the recursion guard, so it is mechanically
safe if ever wanted).

## Decision

Three labels, one markedness principle: **the unmarked word names the unmarked behavior**.
Testing a branch where it stands is what plain CI means everywhere, so it takes the plain
label; the rebase-onto-dev certification is the machinery's special act and takes the compound
name.

| Label | Tree certified | Merge |
|---|---|---|
| `ready-to-integrate` | the branch as-is, no rebase | never |
| `ready-to-rebase-integrate` | rebased onto the `dev` tip | no |
| `ready-to-merge` | rebased onto the `dev` tip | yes — implies the rebase path |

Elements and their laws:

- **The rebase job is the mode reader.** It `gh pr view`s the live labels on every wake and
  emits one `mode` output to `$GITHUB_OUTPUT`: `idle` (no CI label — the wake runs one cheap
  job and touches no ref), `full` (suite runs — as-is or rebased per the tree selector),
  `reuse` (the tested marker matched the fresh rebase; see
  `adr-tested-marker-reuse.md`). Contradictory labels are refused **here**, loudly, before any
  suite minute burns.
- **One contradiction rule:** `ready-to-integrate` cannot stack on either rebase-path label —
  it certifies a different tree, so it contradicts both. To move from as-is to merging, remove
  it and apply `ready-to-merge`; the application itself is the `labeled` wake, so no re-poke
  ceremony. The terminal re-checks live labels as the mid-run race backstop (abort loud).
- **The as-is candidate is the branch head.** The rebase job pushes `+HEAD` as
  `refs/heads/candidate/{N}` with no rebase; the suite certifies that tree; the terminal never
  merges it (no merge label reaches it quietly, a raced-in one aborts loudly). An as-is run
  still stamps the tested marker — a tree certificate is base-agnostic, the probing run's
  fresh rebase binds the base — so an as-is green can legitimately serve a later
  `ready-to-merge` reuse when the trees coincide.
- **The as-is default composes with reuse for free.** A PR cut from the current `dev` tip has
  as-is tree == rebased tree (rebase onto your own base is a no-op), so
  `ready-to-integrate` → green → swap to `ready-to-merge` reuses the certificate and merges
  instantly. The as-is default only pays an extra suite when `dev` actually moved — exactly
  when re-certification is owed anyway. And the first run is never red for foreign reasons:
  conflicts with someone else's dev changes only bite once the rebase path is chosen.
- **The conflict abort teaches the plain label:** "for CI on the branch as-is instead, swap to
  `ready-to-integrate`" — discoverability at the error surface, explicitness preserved.
- **Drafts stay orthogonal.** Labels decide mode, not draft status; the terminal quiet-exits a
  draft (the merge API refuses drafts anyway) *after* stamping the marker, and the wake set
  gains `ready_for_review` so a draft labeled `ready-to-merge` merges when marked ready —
  without it, label-is-state would dead-end at the draft→ready transition with no event. Five
  wakes now: `opened`, `synchronize`, `reopened`, `labeled`, `ready_for_review`.
- **The consumer gates are mode-keyed and lint-mandated.** Every suite job carries
  `if: needs.<rebase>.outputs.mode == 'full'` and needs the rebase job; the terminal carries
  `if: !cancelled() && !failure() && (needs.<suite>.result == 'success' || needs.<rebase>.outputs.mode == 'reuse')`
  — a skipped suite reaches the merge only through the rebase job's proof. The suite gates
  contain no status function, so the auto-`success()` rule keeps a failed or cancelled need
  skipping, and the skipped-need cascade carries an idle or reuse run through to the terminal
  gate, the only continuation point.

## Rejected alternatives

- **A `ci`-vocabulary family** (`ready-for-ci`, `diverged-ci`): "ci" names the activity every
  mode performs; the labels select *which tree* is certified and whether merging follows.
  Operator ruling: not the right names.
- **Rebase as the plain label** (`ready-to-integrate` = rebased, compound for as-is): inverts
  markedness — the special act would wear the plain word, and the as-is lane (which can never
  integrate) would read as integration readiness. Operator ruling: unintuitive.
- **Drafts as the CI gate**: hijacks the review workflow's native signal, forbids CI-on-drafts,
  and dead-ends `ready-to-merge` on drafts with no event to recover.
- **Auto-fallback to as-is on rebase conflict**: silent mode switch, rejected doctrine.
- **Suppress-by-label (default-on CI)**: the `opened` wake burns a suite before any label can
  land; the cheap state should be the one requiring no action.
- **Bot-enforced label exclusivity**: sound but deferred (GITHUB_TOKEN label writes are wake-inert);
  silent bot-chosen resolution and one more workflow per repo, bought before any observed
  contradiction noise.
- **Projects v2 single-select fields**: the only native exclusivity, but no `pull_request`
  activity fires on field edits — nothing wakes the run.

## Accepted costs

1. **The default flip**: unlabeled PRs run nothing (idle, seconds); per-push in-tab feedback is
   gone until a label is applied. Suite spend becomes human-paced — the point of the change.
2. **The swap ceremony**: as-is → merge requires removing `ready-to-integrate` (label removal
   fires no wake; the subsequent `ready-to-merge` application is the wake).
3. **Idle wakes can cancel in-flight suites**: any label application joins the per-ref
   concurrency group with cancel-in-progress; a mid-suite irrelevant label cancels the suite.
   Repair: re-apply the tree-selector label (the standing human repair).
4. **A fifth wake type** (`ready_for_review`) and three-label vocabulary for every consumer's
   humans.
5. **Reopened PRs re-test**: the close sweep deletes the tested marker with everything else.
