# ADR: the fork-contribution lane — a unified two-tier certification model

Status: accepted — D1 through D9 closed, the three side-rulings recorded, and the
foundation verified live: the merge-bot's ruleset bypass carries an API rebase-merge of a
fork PR through `evergreen-dev` (bashrun PR #13, 2026-11-21). D4's transition mechanics are
amended by operator ruling (this branch): the vocabulary lands **additively** — fresh
`approved-for-*` labels beside the untouched `ready-to-merge` row, no in-place rename, no
freeze; the `ready-to-integrate`/`ready-to-rebase-integrate` rows were authored but never
landed live and are dropped from the program (preview-time ruling, 2026-11-21 — no consumer
ever pinned code reading them). D4, D5, and D7 are amended by operator ruling (2026-11-22):
the **review anchor** — a write actor's review at the payload head is the approval, the label
is the command that wakes the run and selects its mode; the amendment notes sit under each
decision.
Implementation follows the queued operator actions. Amends `adr-ci-label-modes.md` (idle mode
gains meaning, the vocabulary moves to `approved-for-*`, fix-push gains a re-approve) and
supersedes the fork-PRs-assumed-nonexistent stance of `adr-api-rebase-merge-landing.md`.
Date: 2026-11-21.

## Context

Fork PRs must certify against the `dev` tip before merging (the evergreen invariant), and
certification means executing the contributor's build code with secrets — the Unity license,
the Android keystore. The exemplar is placeframe-capture-tool PR #24: six Integrate runs
parked at `action_required`, nothing executing, no feedback, the lane undefined.

Everything reduces to one platform fact: there are exactly three run contexts, and every
fork decision is really "which context executes contributor code."

1. **`pull_request` run** — the author's copy of the workflow file (for a fork, the fork's
   own edited copy). Read-only token, zero secrets, platform-enforced; first-time fork
   contributors park at `action_required` until a write actor approves; does not run at all
   while the PR has merge conflicts.
2. **`pull_request_target` run** — the base's workflow file **from the default branch**.
   Read-write token, all secrets, runs through conflicts, PR-associated (checks land in the
   tab natively; reruns replay the frozen payload), exempt from the first-time-contributor
   approval gate.
3. **Push/dispatch runs on refs we create** — trusted, with secrets, but an `on: push` run
   executes the workflow copy **on the pushed ref**. A candidate ref built from fork code
   carries the fork's workflow edits: an `on: push` test lane on rebased candidate refs would
   execute the attacker's workflow file with full secrets. Disqualified as a shape.

The spelling invariant follows: **trusted contexts must execute only base-authored workflow
files while testing fork-authored trees.** Only two trigger spellings satisfy it, and the
lane uses both.

A second invariant discovered en route: the merge endpoint is fork-agnostic (verified by
probe: byte-identical 403 semantics on fork PR #24 and same-repo PR #21; PR #24 reports
MERGEABLE / BLOCKED-by-ruleset exactly as designed). A fork merge under this lane is one
label click plus the existing terminal.

## Decision: the two-tier model, split by labeled-ness (D2, closed)

The lane's architecture is **two tiers split by labeled-ness, not fork-ness** — a unification
that collapsed the originally-sketched member-lane/fork-lane split. Fork-ness appears in no
file, no trigger, no gate. What differs is only the trust the platform itself guarantees,
and the policy consumes that difference in exactly one verb predicate (see D4/D5).

**Tier one — `preflight.yml` (consumer file, trigger `pull_request`).** For every PR, member
or stranger: a secretless check run (lint via `lint-workflows`, release-plan validation,
the python battery) on the unrebased PR head, results in the PR checks tab. Advisory only
— it never certifies, never pushes a ref, never carries a secret-bearing job, never
merges. For forks the platform enforces secretlessness absolutely; for members the
spelling enforces it by never forwarding secrets (lint-checked, adoption-keyed: where the
lane pair exists, no `pull_request`-triggered file references `secrets.*` — `github.token`
and GitHub-provided env are exempt; in unadopted repos the incumbent secret-forwarding
shape stays green until adoption, and the pair-existence rule follows the same key; the
lint polices the committed default-branch shape only, and the member residual is named
under Deferred mechanisms).

Tier one's exact shape: wake set `[opened, synchronize]` — checks pin to the head SHA, so
same-head re-wakes (`reopened`, `ready_for_review`) add only redundant minutes — to `dev`;
concurrency group `preflight-${{ github.ref }}` with cancel-in-progress (a distinct prefix:
both files share `github.ref`, and a shared group string would cross-cancel the tiers); no
`labeled` wake. The battery runs verbatim on the head — a contributor tree that guts
`scripts/preflight.py` or deletes `publish.yml` reds the advisory run, which is the slop
filter working. Head-checkout mode disables the uv cache save (fork runs hold a read-only
token). The tier requires the PR-head checkout spelling: the current composite checkout
hard-fails on the absent candidate ref, so the candidate-resolution logic the old machinery
deleted is reintroduced as an explicit head ref.

**Tier two — `integrate.yml` (consumer file, trigger `pull_request_target`).** Wake set
exactly `[labeled, synchronize, reopened, ready_for_review]` — `synchronize` carries the
strip (D4), `reopened` and `ready_for_review` keep an approved PR from dead-ending at the
close/reopen and draft→ready transitions, and `opened` is dropped (the trigger cannot fire
on a human act; this is the load-bearing difference from tier one). Triggers cannot filter
by label name — every label click anywhere wakes one cheap job that idles unless an
approval label is live; no job-level label `if:` (file minimality). `workflow_dispatch` is
dropped from the consumer file: a dispatch run of a `pull_request_target` file carries a
branch ref, not `refs/pull/{N}/merge`, and the verb's PR-number parse would die loudly.
The default branch's copy of the file, full keys, for every PR. It is the sole context in
the system where secrets and merge authority exist: the standard chain (rebase job reads
live labels for mode, candidate ref, suite with secrets, terminal merge via the bot) over
the payload head. Both tiers are thin consumer switchplates calling the same pinned
toolkit reusables. The lint contract for the pair: both files must co-exist (either found
implies the other), share the pin (already repo-wide law), and the shared preflight call's
`with:` block must be identical in both. The `pull_request_target` file stays minimal — no
script bodies, no interpolation of author-controlled strings (PR titles, fork branch names
appear nowhere; zizmor's template-injection audit mechanically enforces the class). The
dangerous-trigger allowances are path-scoped and enumerated at implementation: the
consumers' `integrate.yml`, this repo's own `_integrate.yml` (the underscore spelling), and
the moved `cleanup-pr-releases.yml` — every zizmor firing on the new files is budgeted
explicitly rather than assumed to be dangerous-triggers alone.

Membership buys exactly one thing under this model: the authority to apply the label. The
label buys secrets. Members' PRs are certified by the incumbent default-branch machinery,
never by their own branch's file edits — a member cannot self-modify their certifier (a
property the fork lane always had; the unification extends it to everyone).

**Consequences of the unification:**

- The certification chain runs in one context for all PRs. The old member path (certify
  inside the `pull_request` wake of the member's branch copy) is deleted; nothing needs
  reintroducing, since the fork-refusal step the old machinery carried was already deleted
  by the `adr-api-rebase-merge-landing.md` follow-up rulings — the sandbox spelling simply
  never certifies anything, for anyone.
- This repo's own consumer files follow the underscore convention: `_preflight.yml`
  beside `_integrate.yml` (a consumer-shaped `preflight.yml` cannot coexist with the
  reusable of the same name), both underscore-normalized by the lint.
- The AGENTS doc ripple is load-bearing and rides this branch spec-first (prose before
  code): this repo's `AGENTS.md` (the five-wake law, the old vocabulary, the permission
  table, the fork-PRs-out-of-scope stance), `adr-ci-label-modes.md`, capture-tool's
  `AGENTS.md`, unity-devkit's `AGENTS.md` (the identity-stamping contract), infra's label
  descriptions, and the vocabulary note in `todo/fork-contribution-model.md`.
- `cleanup-pr-releases.yml` must move to `pull_request_target: [closed]` as well — the
  `pull_request` close event is read-only for fork PRs and cannot sweep the artifacts a
  labeled fork PR now creates.
- The reusables the certification lane calls were hardened when payload data came from
  members; the standing env-indirection law (`AGENTS.md`, invocation grammar) already
  governs author-controlled values end to end, and zizmor enforces it at this repo's own
  preflight. One audit pass over the called reusables against fork-authored payloads is
  lane work, recorded in D8.
- The default-branch flip (D3) is load-bearing: `pull_request_target` reads the default
  branch's spelling, so with default = `main` the certification lane would execute the
  promoted, lagging machinery.

## Decision: the feedback tier's behavior (D1, closed)

Idle mode is redefined from "run nothing" to "run the secretless tier." An unlabeled PR,
fork or same-repo, gets the secretless preflight on its head on every open and push —
secretless, not free: the base repo pays real hosted minutes per run, rationed for
strangers by the first-time approval gate and swept by per-PR concurrency. The
redefinition is realized by tier one's existence, not by a verb change — `mode=idle` in
the rebase verb behaves exactly as before. Suite spend stays
human-paced: the label still gates everything expensive, secret-bearing, or merge-bound.
This amends `adr-ci-label-modes.md` accepted cost 1 and realizes the slop-filter intent of
`todo/fork-contribution-model.md`. A preflight run on the head and a preflight run on the
candidate are two different jobs sharing a verb — advisory preview versus certificate —
and certification can never consume feedback-tier results (the feedback tier executes the
author's own file spelling, untrustworthy by construction for strangers).

## Decision: the default-branch flip (D3, closed)

All 13 evergreen repos flip default branch to `dev`. Committed in infra-github-org
(`3a86213` code, `98de36d` docs; `Repository` gains `default_branch`, one `BranchDefault`
child per repo; smoke-verified at 173 creates before the label and keystore additions —
the count is recomputed at preview time). Pending the operator's push and reviewed `up`,
which lands the flip together with the fresh `approved-for-*` label rows (D4, additive)
and the CI keystore secrets where minted (D6).

## Rejected alternatives (with derivations)

- **One mixed-trigger file** (`pull_request` + `pull_request_target` in one file, disjoint
  activity lists): mechanically possible — each event fires exactly one context — but the
  trust boundary would live in `if:` gates and type-list hygiene rather than in file and
  trigger structure. A typo in a type list silently changes trust posture. zizmor's
  dangerous-triggers audit exists to scream at exactly this shape. Two files cost ~10
  lines of shared `uses:` calls; the lint pins them together.
- **`integrate.yml` switched wholesale to `pull_request_target`:** the trusted context would
  wake the instant any stranger opens a PR, before any human act (the approval gate exempts
  `pull_request_target`). Safety would rest on every job's `if:` gate forever — procedure,
  not structure.
- **Comment-command bot (Prow/bors style):** the labeled event already snapshots the
  approved head (see D4), so SHA-in-text buys nothing; a hosted bot is a standing service
  with a trust-model attack surface (Prow's own bug bounty prices exactly that bypass), and
  an `issue_comment`-triggered workflow re-derives comment→PR→head with permission checks
  to obtain a gesture worse than a label (comments are events that scroll; labels are
  glanceable state — the labels-are-state doctrine).
- **Dispatch lane** (label-gated `pull_request_target` listener dispatching builds on `dev`):
  loses PR association (results need a check-posting bot) and frozen-payload replay (reruns
  could not be trusted to certify the approved head) — two platform properties the lease and
  retry model structurally ride on. Its only advantage, default-branch decoupling, died with
  D3.

## Deferred mechanisms (with trigger conditions)

- **Protected environment with required reviewers** holding exactly the certification
  secrets (`UNITY_*`, the Android keystore quartet — used only by suite build legs; the
  merge-bot key and delivery secrets stay out, so merges and releases stay automated).
  This is the named mechanism for the day membership needs revoking: it upgrades the
  pre-grant guarantee from convention to platform enforcement (jobs referencing the
  environment cannot start or read its secrets until a listed human approves **that run**),
  and it would close the member residual (a member's branch-copy workflow requesting
  secrets pre-label). Not adopted now: approvals are per-run, so every member certification
  and every dev-moved retry (a re-run is a new run and waits again) would pay a human
  click — ceremony on paths ruled hands-off. Switch condition: membership broadens beyond
  vetted collaborators.

## Open decisions

### D4 — closed: the approval is per-head, pushes revoke it; vocabulary moved to `approved-for-*`

Ruling (operator, 2026-11-21): **uniform auto-strip** (the grant-as-event mechanic) with a
**vocabulary move to `approved-for-*`**. The label is applied by a write actor (labels are
write-actor-only;
every `labeled` event is maintainer- or member-initiated) at a specific head, and GitHub
labels persist through pushes — the exact vulnerability class of GHSA-2j2x-r73g-hrr5
(feast), which the GitHub Security Lab had already called "a temporary solution."

- **The grant is the `labeled` event.** An immutable snapshot carrying the exact head the
  approver saw. A `labeled` wake certifies at the payload head: no freshness bookkeeping,
  no recorded state. The event payload is the record — bors' "Commit abc123 approved"
  internalized natively.
- **The certification rule, precisely:** `synchronize` never certifies — it strips, then
  idles. `labeled` certifies at the payload head. `reopened` and `ready_for_review`
  certify on label presence, which is safe because the strip keeps presence equivalent to
  "this exact head is approved" — no push intervened without deleting the label. The
  feast-class defense is scoped to `synchronize` (their bug was a guard accepting presence
  on `synchronize`); it is not a blanket ban on presence-certifying wakes, which would
  dead-end approved PRs at the draft→ready and close→reopen transitions and break the
  dev-moved retry path (reruns replay non-`labeled` actions by design).
- **A `synchronize` wake on a PR carrying an approval label strips the label** and posts
  one explanatory comment ("your push revoked merge approval; a maintainer re-approves
  your changes"). The feedback tier still checks the new head. Label presence therefore
  always means "this exact head is approved" — the state cannot go stale. This is the
  canonical fix per the ecosystem convergence (Prow's `lgtm` strip, bors' `r+` cancel).
  Mechanics: the rebase verb, on entry, before the mode read; the wake's activity type
  rides step env (`PR_EVENT_ACTION: github.event.action` — nothing threads it today);
  strips every `approved-for-*` present; posts the static comment; emits `mode=idle`.
  Label writes and the comment need `pull-requests: write` on the rebase job (the
  consumer-owned permission change, lint-mandated at every call site); the job
  `GITHUB_TOKEN` suffices (label writes are recursion-guard-inert, so no wake loop).
- **Uniform scope.** Stripping applies to member and fork PRs alike. The member ceremony
  is self-service (members hold label authority; the author re-approves their own PR),
  roughly one click per push. Uniform buys state-truth and deliberate arming — every
  merged head carries a human approval click at or near it. It buys no member threat
  defense (a malicious member simply re-approves; the membership residual dominates) and
  is recorded as such.
- **Recovery, both paths:** a red run with a fix is "fix, push" — the strip fires, and
  re-approval re-arms. A red run without a push (a flake) is the re-run — the frozen
  `labeled` payload replays the approved head, the label untouched. Contributor docs
  teach both.
- **Doctrine amendment:** recovery-from-red-with-a-fix becomes "fix, push, re-approve,"
  amending `adr-ci-label-modes.md` and the rerun-lander prose. Reruns stay ceremony-free:
  a re-run replays the frozen payload head (the bevy retry hole stays dead), the lease
  aborts mid-run drift, and a re-run is not a `synchronize` — the strip never touches the
  retry path.
- **Vocabulary:** `ready-to-merge` → `approved-for-merge`; `approved-for-integrate` and
  `approved-for-rebase-integrate` have no live counterparts — the
  `ready-to-integrate`/`ready-to-rebase-integrate` rows never landed and are dropped from
  the program, so the as-is modes exist only in the approved vocabulary. The 2026-11-20 vocabulary named a judgment ("ready") the machinery
  never verifies; post-strip the label is an authority-granted, per-head, revocable,
  deterministic standing approval, and with D5(a) fusing judgment and permission into one
  act, the label replaces GitHub's native approval machinery outright: native reviews gate
  nothing here (zero required approvals, bot bypasses rulesets), wake nothing (no review
  activity type), and the strip-on-push rebuilds dismiss-stale-approvals as enforced.
  Naming it approval claims that territory deliberately and converges with Prow's
  `approved` label. Markedness preserved (plain = as-is, compound = rebase, merge implies
  the rebase path). Prose family term: approval labels. The naming codifies D5(a) — a
  future review gate requires a vocabulary revisit with it.
- **Vocabulary mechanics (amended by operator ruling, superseding the originally-ruled
  in-place rename):** the infra program ADDS three `approved-for-*` `LabelSpec` rows (fresh
  suffixes `approved-merge`/`approved-integrate`/`approved-rebase-integrate` — new creates,
  no create-and-delete pair, no protect dance) and leaves the `ready-to-merge` row
  byte-identical: old-pin consumers match the label by live name, so every byte stays until
  the fleet's last re-pin, its deletion a deliberate cleanup `up` after fleet completion.
  The never-landed `ready-to-integrate`/`ready-to-rebase-integrate` rows are dropped from
  the program rather than upped — live toolkit code has only ever read `ready-to-merge`, so
  the incumbent family is that row alone. The constraint the ruling actually intends is **per-SHA single vocabulary** —
  one toolkit SHA ever reads exactly one label family — which the toolkit's constants
  (`merging.py`, carrying `approved-for-*` on this branch) hold; the live label set
  serves both pins during the transition. The `up` lands before this branch's landing PR so
  the new constants find live labels.
- **The transition is additive, zero-downtime (superseding the freeze):** from the `up`,
  old-pin repos keep certifying and merging on the untouched `ready-to-*` set; each repo's
  re-pin (atomic with adoption) moves it to `approved-for-*` at the operator's pace. Accepted
  window costs, named: both families visible per repo (a wrong-family label idles until
  re-labeled — recoverable, and the idle message names the labels the machinery wants), a
  stale `ready-to-*` on a re-pinned repo is inert (the strip removes only `approved-for-*`),
  and one cleanup `up` retires the old rows after fleet completion. No open-PR verification
  gate is needed — nothing is renamed, so no PR's labels change meaning at the `up`.
- **Amendment (operator ruling, 2026-11-22): the review is the approval.** D5(a)'s
  label-alone grant is superseded. A label carries no commit identity, so a label clicked
  from a stale tab certified whatever head was current — push-then-label was the one race
  neither the strip nor the lease covered. The anchor closes it: a review records the commit
  it examined (`commit_id`), and no non-idle gate run proceeds without one at the payload
  head. The gate reads the PR's submitted reviews, keeps those whose `commit_id` equals the
  checked-out head, and takes the latest by `submitted_at` among write actors (ties broken by
  review id, later winning): `APPROVED` passes, and `CHANGES_REQUESTED`, `COMMENTED`,
  `DISMISSED`, or absence refuses. `PENDING` is not a review. Only write actors' reviews
  count, in both directions — a stranger's `APPROVED` grants nothing and a stranger's
  `CHANGES_REQUESTED` vetoes nothing — and write-ness is measured by the permission call
  (`collaborators/{login}/permission`), never by an association field. Own-PR exemption: a
  PR whose author holds write-or-above permission rides the label alone, because GitHub
  refuses self-approval and the machinery is not a boundary against its own trust root. The
  check runs at gate entry, after the idle return and the stacked-pair refusal and before
  any rebase, mode, or marker work, on every non-idle wake including reuse. A refusal strips
  every `approved-for-*` label, posts one fixed teaching comment, and fails the gate job red
  — red separates a violated precondition from a green idle, and label removal fires no
  wake, so the repair (review at the head, then label) is self-propelling.

### D5 — closed: the approval label is the whole grant; no review gate

Ruling (operator, 2026-11-21): **(a) label alone.** No approving-review requirement on
fork PRs. The label application is both the judgment and the permission — one deliberate
act by a write actor, mechanically the only gate (the ruleset already requires zero
approvals and the bot merge bypasses rulesets). Consequences: the native review surface is
advisory communication with no mechanical role (contributor docs must say so — D7); the
audit trail for every certified head is the labeled event itself (who clicked, which
head, when); and the vocabulary follows — `approved-for-*` names the fused act, replacing
rather than supplementing GitHub's approval machinery. No fork predicate survives in
the verb: post-unification the machinery is fork-blind in policy as well as architecture
— D6's secret scoping is per-channel, not per-actor, so no fork branch exists anywhere.
If rubber-stamping ever becomes a live concern, the revisit is this decision, coupled to
the vocabulary as noted in D4.

**Amendment (operator ruling, 2026-11-22): the label is the command, not the approval.**
The label keeps both mechanical roles — the wake (the only write-act wake
`pull_request_target` offers) and the mode selection — and the `approved-for-*` vocabulary
stands unchanged, naming what the recorded approval is for. What it gives up is the claim
to be the approval itself: that is the review at the payload head (the D4 amendment), so
the native review surface is no longer advisory communication with no mechanical role. The
audit trail for a certified head is the review (who examined which commit) beside the
labeled event. Cost: two deliberate clicks per contributor approval — the review, then the
label — against one for a write actor's own PR.

### D6 — closed: tiered signing keys, per-channel identities, license rides, prereleases publish

Ruling (operator, 2026-11-21), covering all three sub-questions plus the signing-model
correction that emerged from them:

- **Two keystores, tiered.** A new dedicated CI keystore (operator-minted) signs every
  non-main build: the dev channel and every PR build, member and fork. The production
  keystore signs main-channel builds only. Fork certification runs hold exactly the CI
  keystore — its theft value collapses by construction, because suffixed identities mean
  nothing it signs can install over a production install. The debug/churn mode is rejected
  for CI artifacts: a fresh per-runner key breaks within-channel install-over, the exact
  pain this model exists to remove. Secret names `CI_ANDROID_KEYSTORE` /
  `CI_ANDROID_KEYSTORE_PASSWORD` / `CI_ANDROID_KEY_ALIAS` / `CI_ANDROID_KEY_PASSWORD`
  (mirroring the production quartet's shape), infra config fields
  `capture_tool_android_ci_*` (Make-it-Sing at its adoption), added per-repo at adoption.
  **The keystore mint is a precondition of the lane going live** — the interim
  debug-signing fallback is struck: the build leg's quartet inputs are required by
  standing contract, the emptiness guard exists to prevent exactly churn-signing, and no
  temporary weakening rides a window whose length the operator controls.
- **Per-channel application identities.** Bare id for main, `.dev` for the dev channel,
  `.pr{N}` per PR. One derivation, single-sourced in unity-devkit's identity module —
  `channel_suffix(channel, pr_number) -> (id_suffix, display_suffix)`, so `pr` yields
  `(".pr24", " (pr 24)")` and `dev` yields `(".dev", " (dev)")` — derived inside the
  build verb from the channel and PR number it already holds, feeding both stamps: the
  applicationId and the display name, rendered by the Python player_build module beside
  the existing `bundleVersion` stamps (the C# package is untouched; the domain derives
  and renders identity, the binding selects the channel — the derivation is a pure
  function of two facts already on the verb, so nothing binding-owned crosses the seam).
  Version codes stay independent per id via the commit-count stamp.
  Coexistence on one device and install-over-without-uninstall within each channel follow
  from id-plus-stable-key. The model applies to any Android build leg this repo provides;
  no Flutter leg exists (see below).
- **Every channel builds its own artifact, and the shelf keys per channel.** PR
  certification builds the `.pr{N}` artifact (CI key, public prerelease); the dev merge
  push gains a build pass (`.dev`, CI key) where the staple step was — a `build-unity`
  call in the consumer's `release.yml` (the release composite cannot host container
  jobs); promotion gains a build pass (bare id, prod key). Channel threading: a `channel`
  input on `build-unity.yml` (`pr|dev|stable`), the two quartets mapped into the existing
  four secret names per channel at the call site. The builds shelf, keyed `sha-{full}`
  today, gains channel-scoped tags (`{channel}-sha-{full}`): a fast-forward promotion
  makes the dev and main trees share one SHA, and one bare key cannot name two different
  artifacts — a named-contract change landed in lockstep by unity-devkit (push side) and
  this repo (pull side), with `release.py`'s dev/stable resolution moving off the
  `certified/{N}` tag (which after D6 names a `.pr{N}`-stamped, CI-signed artifact that
  must not be stapled) to the run's own build-pass SHA. The dependency chain, recorded:
  per-channel identities alone unconditionally imply the build passes (identity is
  stamped at build time, so no dev or main release can staple a PR-built binary), fork
  secret scoping alone implies them for fork-merged release tips (no prod-signed artifact
  would exist), and only retreating both removes them while forfeiting feature and
  posture together. The invariant bought: the production keystore lives in exactly one
  workflow, on main, post-merge, never in any PR context.
- **The Unity license rides pre-merge fork certification.** Accepted risk, stated: the
  exfil path is real (contributor C# runs at build time, reads env, hosted runners have
  open egress, build logs are public), D5(a) makes the approval click the sole human
  filter, and license revocation is the mitigation of last resort. Deferral rejected: it
  weakens the evergreen invariant for fork merges specifically and surfaces unity
  breakage on `dev` only after the merge.
- **Fork prereleases publish.** Public `pr-{N}` prereleases, CI-signed, suffixed
  identity, same sweep rules (one live prerelease per PR).
- **Scope, acknowledged:** the initiative spans this repo (the certification lane, the
  identity derivation, the release build passes), unity-devkit (identity stamping),
  infra-github-org (the CI keystore quartet), and consumers (per-repo adoption at
  operator pace, D8.1 retired at each repo's flip). The Flutter app inside PR #24 is out
  of scope by operator ruling: its correct home is an entirely new repo, not
  capture-tool — the PR will be redirected or closed accordingly, and no Flutter build
  leg is designed here. Lane verification does not depend on it; the merge-verification
  vehicle is whatever suitable fork PR exists at verification time (a scratch one if
  none).
### D7 — closed: contributor docs are canonical here, verbatim copies in consumers, drift-gated

Ruling (operator, 2026-11-21): author now, riding each consumer's lane-adoption PR,
capture-tool first. The canonical text lives in this repo as package data, following
python-devkit's `ruff.base.toml` pattern: a sync verb writes verbatim copies into the
consuming repo, `--check` byte-compares (newline-normalized) inside preflight so the gate
is merge-gating, cosmetic canonical edits ripple into every consumer's diff by design,
and the canonical's version follows the consumer's toolkit pin.

Adaptations the docs case forces, recorded:

- **Copies are mandatory** (unlike the zizmor config, which is verb-supplied with zero
  consumer copies): GitHub's UI reads `CONTRIBUTING.md` and `PULL_REQUEST_TEMPLATE.md`
  directly from the consumer repo — the same constraint that makes ruff ship a copy
  rather than `--config`: the direct reader (editor for ruff, web UI for docs) must find
  the file in place.
- **No extend layer exists** — GitHub renders the files verbatim — so the canonical is
  100% generic process documentation (target `dev`; CI is human-paced; the feedback tier
  runs automatically after first-time approval; approval here is the `approved-for-*`
  label, not the review button; pushing revokes approval; red = fix, push, re-approve;
  conflicts = rebase onto `dev` and push; prereleases are coinstallable beside dev and
  main builds). Repo-specific deltas are forbidden; project content belongs in READMEs —
  the contributor experience is identical across the fleet.
- **The gate is adoption-keyed**, mirroring the lint's filename-keyed contracts: it
  applies only where both consumer lane files are found (underscore-normalized), so
  unadopted repos stay green. Adoption PRs bring machinery and docs in together;
  thereafter a pin bump that edits the canonical fails preflight until the copies update
  in the same PR (the SHA-law coupling).
- **Mechanics pinned:** the verb is `sync-contributor-docs` (package-data canonical,
  invoked via `uv run --project <toolkit-clone>` at the consumer root, the standing
  binding-verb geometry); destinations are root `CONTRIBUTING.md` and
  `.github/PULL_REQUEST_TEMPLATE.md`; the `--check` runs as a step in the preflight
  reusable (both tiers — early feedback in tier one, merge-gating in tier two).
- **Amendment (2026-11-22):** the canonical teaches the review-then-label sequence — a
  maintainer reviews the code, then labels it — in place of "approval is the label, not the
  review button"; a red run with the labels stripped means "review this head, then label
  again".

### D8 — closed: interim rules until the lane ships

Ruling (operator, 2026-11-21): all three confirmed. The original fork-refusal hack in
the rebase verb is designed out by the D2 unification (the sandbox spelling never
certifies anything, for anyone). Standing until each repo's lane adoption lands:

1. **Never apply an `approved-for-*` label to a fork PR** — the live machinery is the old
   model and a labeled fork PR dies ugly at the candidate push. The rule in
   `todo/fork-contribution-model.md` takes the vocabulary update and stays in force
   per-repo.
2. **The reusable-audit pass** — one deliberate audit of the certification lane's called
   reusables against stranger-authored payloads: every author-controllable value rides
   env, never interpolation (the standing invocation-grammar law; supply-chain audit
   fact 15 is the precedent). Lane implementation work.
3. **The cleanup move** — `cleanup-pr-releases.yml` goes to `pull_request_target:
   [closed]` (the `pull_request` close event is read-only for fork PRs and cannot sweep
   what a labeled fork PR now creates), absent-object paths verified no-op-safe.

### D9 — closed: the live merge proof, performed and on the record

Act (2026-11-21): bashrun PR #13, "merge-probe: validating fork merges," a fork PR from
tyler-s-hatch against `dev`, sat `MERGEABLE / BLOCKED` for non-bypass actors exactly as
designed. A merge-bot installation token (App 5169806, installation 167373481, scoped to
bashrun alone with contents + pull-requests write) called `PUT /pulls/13/merge` with
`merge_method: rebase` and returned **HTTP 200, `merged: true`**. Post-state verified:
the PR closed **MERGED**; `dev`'s tip became the replayed commit `1d1a693`, authored by
the fork account; the fork was never written. The one platform fact everything above
rests on — the merge-bot's `evergreen-dev` bypass carries an API rebase-merge of a fork
PR — is proven live, not inferred. Residue: the one-line probe commit rides bashrun's
`dev` harmlessly.

## Transitions (how the fleet gets from here to the lane)

The ADR's decisions describe states; the machinery's versioning — SHA pins, branch-copy
vs default-copy execution, URN-pinned labels — makes the transitions the hard part. All
of them are ruled here:

- **The lane-adoption PR is unwakeable, by construction.** A PR flipping
  `integrate.yml` from `pull_request` to `pull_request_target` fires neither trigger: the
  branch copy no longer declares the old, and the default branch does not yet declare the
  new. Every in-machinery workaround is a rejected alternative above. **The sanctioned
  path is one merge-bot API rebase-merge per repo for exactly that PR** — the D9-proven
  move — recorded as the standing exception. All other changes land through the machinery.
- **The vocabulary transition (D4, additive):** the `up` (flip + fresh `approved-for-*`
  labels + minted keystores) lands before this branch's landing PR so the new constants find
  live labels; un-repinned repos keep merging on the untouched `ready-to-*` set, and re-pins
  proceed at operator pace — no freeze, no fleet-wide idling. After the fleet's last re-pin,
  one cleanup `up` deletes the `ready-to-*` rows (the protect two-step).
- **Re-pin equals adoption, atomically.** At the new pin the lint demands the new file
  shape, so a consumer cannot take any toolkit update without the whole conversion. The
  lint keys the `integrate` contract on the found trigger word: a `pull_request_target`
  file gets the four-type contract, a plain `pull_request` file keeps the incumbent
  five-type contract (re-pins of not-yet-flipped repos stay green), a mixed-trigger file
  is refused. The pair-existence and no-secrets rules carry the same adoption key: active
  only where the lane pair exists, so pure re-pins and this repo's own pre-adoption files
  stay green. The cost is named: nothing then forces a pinned-new repo to flip — adoption
  pressure is procedural, operator-paced.
- **This repo self-adopts after at least one consumer:** `_integrate.yml`, the new
  `_preflight.yml`, and `_cleanup-pr-releases.yml` convert via the same sanctioned
  merge-bot path, after the flip (its own `pull_request_target` file reads the default
  branch, which must already be `dev`).
- **Parked runs are debris.** The six `action_required` Integrate runs on PR #24 reference
  the old workflow spelling; approving or re-running them executes the old model and dies
  red. Verification uses fresh events only (a new push for tier one, a label for tier
  two); the parked runs are dismissed.

**The operator action queue, consolidated:** push the infra branch and run the reviewed
`up` (flip, fresh approved-for labels, keystores); mint the CI keystore (precondition of lane go-live);
push this branch and open its landing PR (lands through the incumbent machinery, labels
fresh under the new names); the per-repo sanctioned merges for adoption PRs; re-pins at
pace; promotions as usual.

## Platform facts on record

- `pull_request_target` reads the workflow file from the **default branch** (not the PR's
  base branch); runs through merge conflicts; is PR-associated; reruns replay the frozen
  payload; is exempt from the first-time-contributor approval gate.
- `pull_request` fork runs: read-only token, zero secrets, platform-enforced; do not run
  while the PR has conflicts.
- Labels are write-actor-only. GitHub does not remove labels on push. `unlabeled`→`labeled`
  transitions are the only label events; re-applying an applied label is a no-op event-wise.
- `pull_request_target` has no review-submitted activity type; a review click cannot wake
  the trusted lane; `workflow_run` is banned (standing law).
- Reviews carry the head they were made against (`commit_id`).
- Environment approvals: per-run; "a re-run is a new run: its jobs wait again and need a
  new approval"; only persons can approve (not tokens, not `GITHUB_TOKEN`).
- zizmor 1.30.1 `template-injection` taint map (empirical, this repo's supply-chain audit):
  PR title and `github.event` free text fire HIGH; env-indirection is the documented
  remediation; `pull_request.head.sha` and `.number` are recognized immutable.

## Ecosystem convergence

Prow (`ok-to-test` trust label, `lgtm` auto-stripped on push, `approve` PR-scoped), bors
(`r+` records "Commit abc123 approved"; mathlib: "pushing new commits after `bors r+` will
cancel it"), GitHub native (dismiss-stale-approvals), and GHSA-2j2x-r73g-hrr5 (feast: the
label-persistence bypass, with Prow-style stripping named the canonical fix) all converge
on: **the grant is per-head, pushes invalidate it, machinery enforces the invalidation, a
human re-grants.** The bevy variant of the hole (author pushes unreviewed code and triggers
`bors retry`) is structurally absent here: reruns replay the frozen payload head and the
lease aborts on drift.

## Accepted costs

1. Two workflow files per consumer (`preflight.yml`, `integrate.yml`), ~10 lines of shared
   `uses:` calls, lint-pinned to co-existence, a shared pin, and an identical shared
   preflight call.
2. The member pre-label sandbox is convention-enforced, not platform-enforced (same-repo
   `pull_request` runs can access repo secrets if a branch-copy file requests them). Our
   spelling never forwards them; the lint polices the committed default-branch shape
   only — branch copies are outside any lint's reach until they run. Named mitigation
   path: the deferred certification environment.
3. Certification runs the incumbent machinery: a member PR that edits CI is certified by
   the old machinery, its edits taking effect after merge (self-modification defense,
   accepted as a behavior change).
4. Duplicate preflight execution (advisory on the head, certified on the candidate) — two
   different trees, two different jobs; the certified one is the only one that counts.
5. The D4 doctrine amendment: fix-and-push gains a re-approve click (self-service for
   members, maintainer-paced for forks).
6. The additive window: both label families live per repo until its re-pin; a wrong-family
   label idles until re-labeled (recoverable), a stale `ready-to-*` on a re-pinned repo is
   inert, and one cleanup `up` retires the old set after fleet completion (operator ruling,
   superseding the originally-accepted freeze).
7. One sanctioned merge-bot API merge per repo for the lane-adoption PR — a standing
   exception to "everything lands through the machinery," thirteen times plus the
   toolkit's self-adoption.
8. Per-channel build passes add real hosted minutes beyond the "+1 per merge" phrasing:
   every merge pays a dev-channel build, every promotion a main build, on top of
   certification suites that already build. The stable release and the dev merge push go
   from shelf-staple to build.
9. Cross-repo scope of the one initiative: unity-devkit stamping, the infra CI-keystore
   quartet (operator-minted, a go-live precondition), per-repo consumer adoption at
   operator pace.
10. Two deliberate clicks per contributor approval (the review at the head, then the
    label); a write actor's own PR takes one, because GitHub refuses self-approval.
