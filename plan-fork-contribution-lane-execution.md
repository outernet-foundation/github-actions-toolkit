# The fork-contribution lane — remaining code plan

Scope (operator ruling 8, 2026-11-21): this plan finishes the CODE CHANGES for the
fork-contribution lane in exactly three repos — github-actions-toolkit (done, pending
operator review), unity-devkit (next), and placeframe-capture-tool (the canary and the
validator for everything). GitHub Actions runs enter only when validation requires them;
every operational act (push, publish, label, merge) is the operator's, at the operator's
pace, and is not sequenced by this plan.

Out of scope, deliberately (do not re-import): landing/merging the toolkit branch, the
toolkit's self-adoption, fleet rollout to the other evergreen repos, the `ready-to-merge`
cleanup `up`, the Make-it-Sing CI quartet, PR #21/PR #24 handling, and any further
infra-github-org changes.

Authority: `adr-fork-contribution-lane.md` (accepted; its fleet-wide transition language
is the machinery's capability, not this plan's scope). The day-to-day authority for the
shipped toolkit code is that repo's AGENTS.md.

## Operator rulings ledger (all bind)

1. One sanctioned merge-bot API merge per repo for lane-adoption PRs (ADR).
2. The vocabulary transition lands additively (ADR).
3. No interim debug-signing fallback; the keystore mint is a go-live precondition (ADR).
4. The Flutter app of PR #24 is out of scope (ADR).
5. Tier one's wake set is exactly `[opened, synchronize]` (ADR).
6. The never-landed `ready-to-integrate`/`ready-to-rebase-integrate` rows are dropped
   from the infra program; the incumbent family is `ready-to-merge` alone; the as-is
   modes exist only in the `approved-for-*` vocabulary.
7. Authoring proceeds in parallel against the pushed toolkit branch tip; workflow pins
   are provisional at branch tips, and the final pin value is whatever merged SHA the
   operator blesses at validation time.
8. Scope redefinition: this plan is code changes only; capture-tool is the validator.

## Session state (2026-11-21, entry point for the next session)

**infra-github-org — DONE, landed, pushed.** The reviewed `up` ran after a verified
preview (+60 creates / ~14 updates / 116 unchanged / 0 deletes) with an empty preview
after: the three `approved-for-*` labels live beside the untouched `ready-to-merge` on
every evergreen repo, the thirteen default branches are `dev`, and the capture-tool
`CI_ANDROID_*` quartet is live. The CI keystore is minted and archived by the operator
(sitting artifacts under `/workspace/scratch/ci-android-keystore`; the config values are
secure-wrapped in the committed `Pulumi.dev.yaml`). Infra's own AGENTS.md records the
four-label window and the 190-create smoke. Nothing further belongs to this plan.

**github-actions-toolkit — code complete, pushed, awaiting operator review; amended by the
second sitting (two unpushed commits).** Branch
`fork-contribution-lane` (over `adr-merge-gate-auto-rebase`, over origin/dev). Shipped, verified at those commits: 245 pytest green; self-lint exit 0 against
this repo's own old-shape files (the transition-tolerance proof); basedpyright + ruff
clean; zizmor allowances verified against the pinned 1.30.1 binary with scratch-tree
positive and negative controls. The branch carries: the prose ripple; the label-constants
rename to `approved-for-*`; strip-on-synchronize + `PR_EVENT_ACTION` threading + the
rebase permissions raise; the preflight reusable's `head-checkout` input; the
trigger-keyed lint contracts with pair rules, no-secrets, and the cleanup contract; the
zizmor path-scoped allowances; the build-unity `channel` input + threading (the identity
suffixes derive in unity-devkit's verb from the channel and PR number it already holds);
release's build-pass SHA resolution + channel-scoped shelf
pulls; the `sync-contributor-docs` verb with canonical docs + drift gate; and the
self-check extensions. The amendment: `build-unity.yml` threads `--channel` to the
build verb, with the
AGENTS.md switch-order sentences updated; battery re-verified green (245 pytest, ruff,
basedpyright, self-lint). Post-validation rename (third sitting): the `rebase` job/verb/reusable is now
`gate` — the doorman role, named for the mode gates it feeds; git-operation vocabulary and
the `approved-for-rebase-integrate` label are unchanged, and unity-devkit plus capture-tool
re-pin to the renamed tip in their follow-up commits.

The D8.2 reusable audit record: (1) no template-injection violations —
`github.head_ref` → `BRANCH_NAME` in build-docker.yml is the fleet's one
author-controlled value and already rides step env; (2) `container: ${{ matrix.editor-image }}`
is author-influenced via the head tree's matrix verb — accepted, not shell-injectable,
the certification context executes author code by design; (3) tier two's preflight job
must carry `contents: read` at every consumer spelling — folded into the canary's
tier-two shape below; invisible to lint across the `uses:` wall.

Live validation is available at any time, operator's click: `approved-for-rebase-integrate`
on a PR from this branch wakes the incumbent machinery at the branch-pinned SHA — full
rebase + suite + PR-build release — and the merge verb exits quiet without
`approved-for-merge`. Full live validation, zero merge risk.

**unity-devkit — code complete on branch `channel-identity` (4 commits over dev,
unpushed).** Item 19 prose; Item 20 identity stamping (`productName` scalar append,
`applicationIdentifier` Android entry via a map-aware anchored replace, exactly-once,
refusing an inline-empty map); Item 21 shelf grammar (`builds_tag(channel, sha)`
validated loudly, the CI push dual-tagging `{cache_key}` + `{channel}-sha-{full}`,
`install --sha` composing it with `--channel` defaulting to `dev`). The D6 re-pin rode
as the incumbent-machinery conversion: the old pin `47e2945` predates the rerun-lander
(no `rebase.yml`/`merge-if-ready.yml` existed there), so the pin bump and the conversion
were inseparable — `merge-gate.yml` deleted, `integrate.yml` rebuilt on the incumbent
chain (rebase → preflight → compile-check-unity → release-pr-builds → terminal under the
merge queue, mode gates throughout, `retry.yml` shim added), `release.yml` and
`cleanup-pr-releases.yml` re-pinned. All nine refs at the amended toolkit tip
`3c9a852ede439e0d3a8f2d0eef9e1637dffd34db` (provisional, ruling 7 — the toolkit push
must precede any run). Verified: 65 pytest green; ruff + basedpyright clean;
`preflight-python` OK; and the toolkit's `lint-workflows` green against the converted
tree (actionlint, zizmor, the SHA law, every trigger-keyed contract — one lint-driven
correction: the terminal reuse gate keys on `needs.release-pr-builds.result`, the
terminal's non-rebase need).

**placeframe-capture-tool — NOT STARTED. The canary/validator branch (items below).**
Mechanical preconditions: the relock consumes a PUBLISHED unity-devkit version carrying
the new flags (the publish is the operator's, whenever validation needs it); the
`CI_ANDROID_*` quartet is already live.

**Next-session order:** read this plan → operator gates (push both branches, the
toolkit first — the unity-devkit pin names its amended tip; review the toolkit branch;
the unity-devkit PR lands through its own converted machinery at the new pin, reading
the live `approved-for-*` labels; the merge push publishes unity-devkit — the relock
target) → capture-tool Items 23–24 (the relock alone waits on the publish), at operator
pace.

---

## Phase 2 — unity-devkit: identity stamping + shelf grammar

### Item 19 — unity-devkit AGENTS.md prose `[agent]`
- **Repo:** unity-devkit. **Files:** `AGENTS.md` — the identity-stamping contract (the
  binding derives, the domain renders; the new flag pair as public API across the
  seam), the builds-shelf channel-scoped tag grammar as the cross-repo named contract
  with the binding's pull side. **Prose commit first.**
- **Depends on:** the toolkit branch's flag/tag spellings (Items 11–13 of the former
  plan, shipped). **Verification:** review.

### Item 20 — player_build identity stamping `[agent]`
- **Repo:** unity-devkit. **Files:**
  `packages/python/unity-devkit/src/unity_devkit/player_build.py` — beside the existing
  `bundleVersion` stamps in `build_player`: when the suffix pair is supplied, stamp
  `productName: {name}{display_suffix}` (the existing scalar `replace_serialized_field`
  mechanism) and the `applicationIdentifier` Android map entry (`bundleName: com.…`
  under the `Android:` sub-map — a new map-aware anchored replace with the same
  exactly-once guard; the current helper is scalar-only);
  `packages/python/unity-devkit/src/unity_devkit/build_unity.py` — the suffix pair
  derived in-verb from `--channel` + `--pr-number` via `identity.channel_suffix` (empty
  channel = bare identity, the local build; `pr` without a PR number fails loudly);
  `tests/test_build_player.py` (stamp present/absent/refuse-missing-
  field/count-mismatch). **The C# playerbuild package is untouched** (the Python
  module renders; identity is ProjectSettings, not env).
- **Depends on:** the shipped toolkit side (the `--channel` threading).
  **Verification:** pytest; a local stamp smoke against a scratch `ProjectSettings.asset`.

### Item 21 — builds-shelf channel-scoped keying (push side) `[agent]`
- **Repo:** unity-devkit. **Files:** `packages/python/unity-devkit/src/unity_devkit/identity.py`
  (the builds-shelf tag grammar gains the channel scope: app-binary artifacts dual-tag
  `{cache_key}` + `{channel}-sha-{full}`; the unity-library cache grammar is unchanged —
  its `-pr-{N}`/`-dev` suffixes already scope it), `build_unity.py` (the push side
  composes the channel-scoped tag — `--channel`-shaped input threading per the
  toolkit's env), `install.py` (`--sha` pulls compose `{channel}-sha-{sha}`, dev the
  default; a `--channel` override for PR artifacts), tests, `AGENTS.md` (the grammar
  note rides Item 19's prose).
- **Depends on:** Item 20 (same files). **Verification:** pytest on the grammar; the
  cross-repo lockstep with the toolkit's shipped pull side called out in both
  AGENTS.md files.

The branch may also re-pin unity-devkit's own workflow `uses:` refs to the toolkit
branch tip (provisional, ruling 7) so its own CI exercises the new pin; the final pin
value is the operator's choice at validation time.

---

## Phase 3 — placeframe-capture-tool: the canary/validator branch

One branch carries the whole conversion. Re-pin is atomic with adoption — the pin bump
and the whole file conversion land together (the lint's pair rules refuse piecemeal).

### Item 23 — capture-tool AGENTS.md prose `[agent]`
- **Repo:** placeframe-capture-tool. **Files:** `AGENTS.md` — the branches/release
  section rewritten: six workflow files (tier one added), the two-tier wake sets, the
  approval-label ontology, the strip, the CI quartet, per-channel identities, the build
  passes, the contributor-docs law. **Prose commit first on the branch.**
- **Depends on:** nothing. **Verification:** review.

### Item 24 — the canary branch `[agent]`
- **Repo:** placeframe-capture-tool. **Files and changes:**
  - All workflow `uses:` refs (`integrate.yml`, `cleanup-pr-releases.yml`, `retry.yml`,
    the release composite refs) → the provisional pin (the toolkit branch tip; ruling
    7). One SHA everywhere (the standing law).
  - New `.github/workflows/preflight.yml` (tier one): `on: pull_request: branches:
    [dev], types: [opened, synchronize]`; `concurrency: preflight-${{ github.ref }}` +
    cancel-in-progress; `permissions: contents: read`; one job calling the toolkit
    preflight reusable with `head-checkout: true`; no `secrets:` anywhere.
  - `.github/workflows/integrate.yml` (tier two): trigger →
    `pull_request_target: branches: [dev], types: [labeled, synchronize, reopened,
    ready_for_review]`; **`workflow_dispatch` dropped**; the rebase job's permissions
    gain `pull-requests: write`; the preflight job on the candidate carries
    `contents: read` (D8.2 finding 3 — invisible to lint across the `uses:` wall);
    the build-unity call gains `channel: pr` (the default — may be spelled explicitly)
    and forwards the **CI quartet** (`ci-android-keystore: ${{ secrets.CI_ANDROID_KEYSTORE }}`
    etc. — mapped into the existing four secret names); everything else (mirror,
    preflight on candidate, build legs, mode gates, `release-pr-builds`, the terminal
    under the merge queue) unchanged.
  - `.github/workflows/cleanup-pr-releases.yml`: trigger →
    `pull_request_target: [closed]`; the `merged == false` gate stays (the machinery
    sweeps its own merges; the shim covers manual/unmerged closes — idempotent either
    way).
  - `.github/workflows/release.yml` — the two build passes: a `build-dev` job
    (`if: github.ref == 'refs/heads/dev'`, `uses: build-unity.yml` with `channel: dev`,
    unity trio + **CI quartet**, `permissions: contents: read, packages: write`) with
    the `prerelease` job gaining `needs: [build-dev]`; a `build-main` job (`if:
    github.ref == 'refs/heads/main'`, `channel: stable`, unity trio + **production**
    quartet) with the `release` job gaining `needs: [build-main]`. The delivery
    composite staples from the shelf at the build pass's own SHA. **The production
    keystore lives in exactly this one workflow, on main, post-merge, never in any PR
    context** (the structural invariant).
  - Root `CONTRIBUTING.md` + `.github/PULL_REQUEST_TEMPLATE.md` — written by
    `sync-contributor-docs` from a toolkit clone at the pin.
  - `uv.lock` — relock to the published unity-devkit carrying Items 20–21 (the publish
    is the operator's; the relock cannot precede it).
- **Depends on:** the toolkit branch content (shipped, at the provisional pin); the
  unity-devkit publish (for the relock); the `CI_ANDROID_*` quartet (live, done).
  **Verification:** tier-one advisory run on the PR's own head (the branch copy of
  `preflight.yml` is `pull_request`-triggered — the PR gets live secretless feedback);
  the branch lint green (lane-shaped files at the pin); `uv run preflight-python`
  locally.

Load-bearing knowledge for whoever lands it: the adoption PR is unwakeable by
construction — its branch copy declares only `pull_request_target`, and the default
branch does not yet carry it — so it cannot self-merge; any merge is the operator's
API move (ruling 1), at operator timing.

---

## Validation annex (live, operator-paced; the canary exercises everything)

1. **Tier one, same-repo push:** a fresh push wakes `preflight.yml` on the head; the
   advisory run is secretless (zero `secrets.*` in the run), renders in the checks tab,
   and per-PR concurrency cancels a stale wake.
2. **Tier one, first-time fork contributor:** the run parks at `action_required`; the
   operator's one approval click releases it; the contributor tree's own spelling runs
   (a gutted `scripts/preflight.py` or deleted `publish.yml` reds the advisory run —
   the slop filter working).
3. **Tier two grant:** `approved-for-merge` (or `approved-for-rebase-integrate` for a
   certify-only pass) wakes the `pull_request_target` run from `dev`'s file; the rebase
   job reads live labels, pushes `candidate/{N}`, the suite runs with the Unity license
   and **exactly the CI keystore**; the checks land in the PR tab natively.
4. **Identity:** the build log/manifest shows `applicationId` suffixed `.pr{N}` and the
   display name suffixed ` (pr N)`; `apksigner verify --print-certs` shows the CI
   certificate; the artifact installs beside a production install (coexistence) and
   over a prior same-PR build (within-channel install-over).
5. **Strip:** a push under an approval label removes every `approved-for-*`, posts the
   one static comment, and the run emits `mode=idle`; tier one still checks the new
   head; re-approval (a fresh `labeled` event) re-arms and certifies the new head.
6. **Rerun safety:** re-running a red certified run replays the frozen `labeled`
   payload — no strip, the approved head re-tested; the dev-moved path dispatches the
   retry shim and the next attempt re-rebases.
7. **Prerelease:** `pr-{N}-{count}` publishes publicly, CI-signed, suffixed identity;
   the sweep leaves exactly one live prerelease per PR.
8. **Merge:** the terminal runs under the merge queue; an API rebase-merge lands under
   the lease; the PR closes **Merged** with attribution; the fork was never written;
   the candidate ref, tested marker, and head branch are deleted; `pr-{N}-*` swept; the
   unity-library cache promoted (`-pr-{N}` → `-dev`).
9. **Dev build pass:** the merge push cuts `dev-{count}` from a **freshly built**
   `.dev`-suffixed, CI-signed artifact shelved under `dev-sha-{full}` — nothing
   stapled from a PR-built binary.
10. **Promotion:** the FF `dev`→`main` push builds the bare-id artifact with the
    production keystore in the main job only; the CalVer release staples it; the prod
    quartet appears in no PR-context run anywhere (grep the workflow spellings).
11. **Gates:** a pin bump that edits the canonical docs fails preflight until the
    consumer copies update in the same PR; pair-existence, no-secrets, and
    mixed-trigger refusals each demonstrated once on a scratch branch.

---

## Decisions that still govern the remaining work

- **D3 — shelf prefix spelling.** `{channel}-sha-{full}` uses the channel input's own
  domain: `pr-`/`dev-`/`stable-` (the ADR's "bare id for main" maps to `stable`; `main`
  is never a channel value).
- **D4 — docker shards stay bare.** Channel scoping applies to app-binary shelf
  artifacts only (the signing-identity collision is its entire motivation); docker
  digest shards keep `sha-{full}-{key8}` (identity-free, channel-identical bits).
- **D6 — a re-pin PR lands through the incumbent machinery.** The re-pin rides the repo's
  next branch: the branch copy (old trigger) at the new pin runs the new code reading the
  live `approved-for-*` labels (additive ruling 2/ruling 6 keep both vocabularies live);
  unity-devkit's stamping branch therefore carries its own re-pin.

## Doc ripple (prose never shares a commit with code)

| Repo | Prose | Rides | Before |
|---|---|---|---|
| unity-devkit | AGENTS.md (stamping contract, shelf grammar) — Item 19 | its branch | Items 20–21 code |
| capture-tool | AGENTS.md (six files, tiers, CI quartet, build passes) — Item 23 | canary branch | Item 24 code |
