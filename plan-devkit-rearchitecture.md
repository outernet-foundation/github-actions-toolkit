# Devkit rearchitecture — binding-layer consolidation, package split, fleet cutover

Status: consolidates and supersedes `release-devkit-finish.md`, `ci-refresh-seed.md` (folded
into Phase 7), `zizmor-audit.md` (live gated items folded here; residue in
`todo/supply-chain-control.md`'s appendix), and `plan-reusable-workflow-migration.md`
(subsumed). Decisions below are binding for execution sessions. Cadence: one session per PR
where practical, each landing on `dev` — for this repo itself currently by operator push
(ruling: the repo's own merge-gate is not worth it, may be repaired later; consumers keep the
merge-gate) — each session sized to the context-window smart zone (operator ruling) —
exploration, edits, and verification all fit without degradation, and when in doubt, split;
commit discipline per AGENTS-SHARED (prose and code in separate commits, no trailers).

## Execution state

Landed: Phase 1 (build-artifact-registry renamed, on dev, publishing — `0.1`, then the
registry-auth neutral-env API bump to `0.2`); Phase 5 executed early (python-devkit `0.3`:
the deptry-src fix, `ci_step` deleted, the ci-devkit dependency dissolved); Phase 0 + Phase 2
on dev — certified head `d982657`, landed by the operator's direct push (see the landing
ruling in the status paragraph and AGENTS.md "Landing changes") — riding the matrix/version
refactor, the run-fact partition, the `$/` install-trio flip, and the relock onto
python-devkit `>=0.3.0.dev0`. The repo's current AGENTS.md describes the landed binding
surface in full; the plan does not repeat it. dev is pushed through `3268439` (past `d982657`:
the unity legs' git safe-directory pre-step + its AGENTS.md row, the direct-push landing
ruling, the cleanup-tag fix, and plan records) — pushes are operator-owned. Standing rulings from the landed phases: version
floors spell `>=X.Y.Z.dev0` (PEP 440 — a `.dev` prerelease cannot resolve under a short
base, and a run-id-keyed floor would die on the first count-keyed republish); the old
ci-devkit distribution is frozen forever, no yank; preflight's sequential
lint→plan→script steps are fail-fast economics (the accepted premium over a parallel max()
is one lint wall-clock per green PR), and lint-in-integrate is certification for trusted
authors, never a security boundary — PR-authored YAML can simply delete it (the PPE class
of threats is answered by Phase 7's org-level rulesets, not by lint placement).

Phase 3 (unity-devkit) landed: the relock onto the cache-self-auth prerelease moved the exact
pin to `build-artifact-registry==0.2.0.dev38101394871` (`uv lock --refresh --upgrade-package
build-artifact-registry` — both the plain lock and plain `--upgrade-package` silently kept the
stale pin off a warm index cache; the sweep's relocks carry `--refresh`), integrate went fully
green including the unity compile leg on the self-hosted pool (the cache fix's first live
certification), the labeled merge-gate landed PR #8 as `85e66c1`, and `unity-devkit 0.3.0.dev223`
rode its release.yml onto PyPI. The landing surfaced one bug, fixed on this repo's dev
(`4e12952`, pushed — dev is through `3268439`): the merge-gate run goes red after every real step — `gh release delete
--cleanup-tag` 422s on the pr draft because a draft never materializes its tag until publish
and these drafts are never published; `--cleanup-tag` is dropped from `delete_draft_release`
(both call sites — `pr-{N}` and the stable channel's `dev-builds` reset — delete never-published
drafts). Standing reading: a red merge-gate conclusion on a pre-fix pin means nothing once the
merge, branch-delete, and draft-delete lines have printed; the sweep's one fresh toolkit SHA
carries the fix atomically with every cutover. Wrapper bump and cutover stay one atomic step
per repo (a wrapper bump past d982657 alone forces the labeled-only wake and the strict-lint
findings onto un-migrated files — Phase 7's cutover spells the atomicity). Transitional noise,
self-healing: unity-devkit's main still carries the old workflow_run-woken merge-gate.yml,
failing loudly on the now-required `--head-sha` until main receives the new file (dev → main
promotion or the sweep). Phase 4 (docker-devkit) landed: PR #10 merged as `7c82d56`, riding
`build --push` over the neutral `REGISTRY`/`REGISTRY_TOKEN`/`REGISTRY_USERNAME` env (flag
order mirrors the binding run line; `--targets` accepts both repeated flags and one
space-joined value), `docker-build-matrix` emitting bare leg lists with the cross-compile
cohort (`x-cross-compile-targets` ∪ any service declaring `platforms:`) split into its own
variant×cohort legs — a group spanning cohort membership is a loud error; leg schema stays
`{targets, variant}`, named contract — the line bumped `0.2` → `0.3` with the ci-devkit
dependency swapped for build-artifact-registry (the dev group also relocked onto python-devkit
`>=0.3.0.dev0`, removing the frozen distribution from the lock entirely), and `0.3.0.dev113`
rode release.yml onto PyPI. New diagnosis from this phase: the digest-manifest shelf push
(landed on docker-devkit dev via PRs #5–#9, never live — every consumer locked 0.1.23) was
last-writer-wins across parallel legs at one shared `sha-{full}` tag; the Phase 4 matrix
makes fanout the only shape, so the defect would have fired at placeframe's cutover. Fix
(landed, both sides): each leg shelves its own shard `sha-{full}-{key8-of-sorted-targets}`
(docker-devkit side), and the toolkit's `pull_digest_manifest` enumerates a SHA's shards and
merges at pull time — consumption only ever runs after every leg finished, so the merge is
race-free where a push-side merge could not be; the bare `sha-{full}` tag remains a
one-shard fallback. The landing order held: the toolkit's dev pushed first (through `84b0e14`,
which carries the shard merge), then docker-devkit landed. Capture-tool's pilot docker fanout
is ONE leg (all three services are cohort, one common cell — invocation-identical to today's
hand-enumerated job); placeframe's is three (common/cuda/rocm), the first live exercise of the
shard merge. The landing's merge-gate run went red after the real steps — the same cleanup-tag
422 (`gh release delete pr-10 --cleanup-tag`), because docker-devkit's toolkit pin predates
`4e12952`; the pin also predates the toolkit's 3.13 pin (the merge-gate clone's venv resolved
3.15 — the stall pattern, survived). The PR merged and published; the `pr-10` draft lingers
(hidden, the accepted leak). Consequence: every pre-sweep consumer landing through a
pre-`4e12952` pin takes this red-after-success; docker-devkit's workflows are already the
post-migration shape, so a plain repin of its `uses:` refs to a fresh toolkit SHA (≥ `84b0e14`)
is atomic-safe and clears both the 422 and the 3.15 stall — the cheap candidate before the
sweep, same class as build-artifact-registry's carry below. The Phase 6 pilots and the Phase 7
sweep follow.
Phase 6 (bashrun pilot) in flight: PR #8 (`0.6.x`) open on dev, integrate green — the
preflight and update-pr-draft-release reusables' first live consumer passes; the sidecar
relocked onto python-devkit `0.3.0.dev38096025533` (ci-devkit dissolved out of the lock,
Phase 5's claim confirmed live); `scripts/preflight.py` is the two-line sidecar dogfood the
harness invokes. Spec fix riding the pilot: `update-pr-draft-release` job permissions are
`contents: write, packages: read` — the pr channel's draft writes need the write half the
canonical example omitted. The labeled gate call deadlocked (run canceled before any job:
"deadlock detected for concurrency group 'merge-gate-{N}' between a top level workflow and
'merge-gate'") — the reusable carried its own top-level concurrency group identical to the
caller's. No prior landing had exercised the gate as a reusable: unity-devkit PR #8 and
docker-devkit PR #10 both landed through wrapper-shaped local callers, so the pilot was the
first live `workflow_call`. Fix: merge-gate.yml purified to workflow_call-only (own trigger,
top-level concurrency, and the job-level label `if:` dropped — the verb owns all policy);
lint law added — a found file declaring `workflow_call` is a reusable and must declare it as
its only trigger with no top-level concurrency, filename-keyed consumer contracts applying
only to non-reusables; consumer files unchanged; bashrun repins to the fix SHA. bashrun's
main still fires its old workflow_run-woken gate red on integrate completions (the
unity-devkit transitional-noise class) until dev → main promotion carries the new file. The
PyPI-through-composite verification gate is effectively pre-answered: docker-devkit's
`0.3.0.dev113` rode the composite release.yml onto PyPI at Phase 4's landing; bashrun's
landing re-exercises it on the preflight+gate path. Second pilot finding, live-diagnosed: the
reusable cutover renames check runs from bare job names to two-part `caller / called` names
(`preflight` → `preflight / preflight`), and two name-exact contracts still spelled the bare
names. One: the `evergreen-dev` ruleset's required check `preflight` never matched again —
GitHub posts the expectation forever, a pending required check with no associated action on
the PR page. Resolution (operator ruling): required checks are REMOVED from evergreen-dev
entirely — the ruleset carries ref mechanics only; check policy lives in the gate verb's
all-green battery, the sole writer (merge-bot) bypasses ruleset evaluation anyway, and a
ruleset-level check couples the program to check names that drift on every cutover (no
per-repo infra work rides future cutovers; the deletion lands on infra-github-org dev as
`e0e91c4` + its AGENTS.md row). Two: the gate's own self-exclusion demanded its own check
green — the 02:40 run refused "pending" 51s after integrate went green, its own in-progress
check the only pending entry. Fix (toolkit `decae45`): `merge_battery` excludes both the bare
and the two-part spelling of the gate's own check name. Gate check spellings are standing
contract data for anything name-matching checks; the repo-side residue is none — consumers
hold no name-coupled contracts. The gate then landed PR #8 cleanly (`128fca4`, dev) — the
purified reusable's first green landing, self-exclusion fix certified live. Correction of the
earlier record: docker-devkit's `0.3.0.dev113` and unity-devkit's `0.3.0.dev223` rode
OLD-shape release.yml files — the release composite's dev channel had never run live before
bashrun's landing, and its first exercise tripped the boolean ternary: `inputs.stable`
stringified as `"false"` is truthy, so `inputs.stable && 'stable' || 'dev'` resolved stable
inside the dev job — it published bare `bashrun 0.6.0` to PyPI (content-identical to the
landed tree, untagged), then died pushing `bashrun-v0.6.0` (the dev composite never persists
credentials, by design). Fix (`feef989`): `inputs.stable == true && 'stable' || 'dev'`.
Operator ruling on the stray: no yank — bashrun bumps `major_minor` to 0.7, the untagged
0.6.0 stays on PyPI as an orphan (version math is tag-driven and never references it), the
next dev publish is `0.7.0.dev{count}`, the eventual promotion publishes stable `0.7.0` and
tags `bashrun-v0.7.0`. The PR #9 landing then rode the fixed composite green —
`bashrun 0.7.0.dev83` live on PyPI, the dev channel's first correct run; PR #9's integrate
and gate certified at `315814d`. The first-ever promotion surfaced the last piece:
`main-append-only`'s `required_linear_history` rejected the fast-forward push ("must not
contain merge commits") because dev's tips are the gate's `--no-ff` merge commits. Ruling
(2026-10-11): promotion is a pure fast-forward pointer move of dev's tip — the cargo includes
bors merge commits by design, and the stable channel's parent-split requires a merge-commit
tip; the flag is removed from `main-append-only` (infra `dev`, `44a5c1e` + AGENTS.md
`e3edd29` — fast-forward + undeletable stay, evergreen-main's operator-only update rule
stays). The correct main envelope is exactly: only the operator updates, updates are
fast-forwards, deletion blocked for everyone; "main only ever advances to a promoted dev
SHA" remains procedural (no ruleset primitive binds a tip to another branch). The promotion
then passed (main = dev = `cc809cb`, the phantom workflow_run gate on main dying with it —
main now carries the labeled-only file), but the stable channel — its first live exercise —
executed the DEV channel and went green doing it (run 38107631822): it built
`bashrun-0.7.0.dev83`, `uv publish --check-url` skipped the upload (PR #9's landing already
published that version), it appended a dev-builds section, pushed no `bashrun-v0.7.0` tag,
cut no CalVer release, and reset nothing. PyPI carries NO `0.7.0`.

OPEN ISSUE (next session diagnoses; this one closed by operator ruling before landing a
second fix): the release composite's channel selection from the `stable` boolean input.
Composite inputs ride stringified inside `${{ }}` expressions, and both expression forms are
now live-proven broken in opposite directions — v1 `inputs.stable && 'stable' || 'dev'`
read the stringified `"false"` as truthy (the dev job ran stable at PR #8's landing,
publishing the untagged `0.6.0` orphan); v2 `inputs.stable == true && 'stable' || 'dev'`
(`feef989`) number-casts the stringified `"true"` away from boolean true (the stable job
ran dev at the promotion). Any fix must stop evaluating the input in GitHub expressions
entirely; `persist-credentials: ${{ inputs.stable }}` (direct forwarding into a typed
action input) is correct and unaffected. One shape was drafted and REVERTED unlanded
(operator abort): `STABLE: ${{ inputs.stable }}` riding step env — the env crossing
stringifies deterministically — with an `if [ "$STABLE" = "true" ]` bash branch selecting
the channel beside the existing run line. The next session re-derives or replaces it; the
toolkit AGENTS.md flags the current expression as broken so no session trusts it.

Recovery sequence once the composite is fixed: land the fix on toolkit dev; bashrun repins
its `uses:` refs through the gate (branch off the current dev tip — local clones lag
origin after runner-side merges; the operator pulls, the agent never fetches and never
uses prepo); the landing's dev channel publishes the next `0.7.0.dev{count}`; then the
operator re-promotes `dev:main` (fast-forward) and the stable channel runs its first
correct pass — publishes `0.7.0`, tags `bashrun-v0.7.0`, cuts CalVer `2026.10.4`, resets
`dev-builds`. Re-running 38107631822 is useless: a rerun re-executes the composite at the
SHA cc809cb's release.yml pins (the broken v2), and release.yml has no workflow_dispatch
trigger. Pilot state otherwise standing: preflight and the gate reusable certified on two
landings; the composite dev channel certified (`0.7.0.dev83` live on PyPI); trusted
publishing through composite-wrapped steps accepted; the stray `0.6.0` orphan stays by
ruling; placeframe-capture-tool pilot and the Phase 7 sweep remain.
Open carries, decisions pending: build-artifact-registry's own CI resolves 3.15 in the
wrapper-driven jobs — its wrapper pins `029a9a6`, a
pre-rearchitecture toolkit tip that predates the toolkit's 3.13 pin, and `uv run --project`
discovers the interpreter from the clone (the repo's own pin cannot reach it; `tools/devkit`
lacks a `.python-version` as a secondary door; its repo CI keeps the hand-written shape
until the Phase 7 sweep). Candidates: wrapper bump to the pushed head `3268439` (requires the
merge-gate wake fix and `release-devkit.yaml` migration to `registry:`+`identity:` — the new loader
hard-flips the old `registries:` spelling) vs job-level `python-version` pins on the
setup-uv steps. Also: its origin remote still spells the ci-devkit SSH URL (redirects cover
it; rename housekeeping is host-side). Correction of an earlier record: `gh` is NOT blind to
Actions runs — the App token minted via `uv run --project /pulsar/scripts
mint-github-app-token` reads run lists, views, and logs on the public repos; the prior
session's "verified live" 401 was the ambient ghcr-scoped `GITHUB_TOKEN`, not the App's
capability boundary.

Fleet interpreter pins (CPython 3.15 drift incident): uv 0.11.x offers managed 3.15.0, and
every repo with an unbounded `requires-python = ">=3.13"` let fresh runners resolve 3.15 —
whose lock pins (pydantic-core 2.46.5 and friends) ship no cp315 wheels, so every
wrapper-clone `uv run --project` built the pydantic-core Rust sdist: multi-minute silent
stalls (pinned repos were immune). Resolution: `.python-version` pins (`3.13`);
`requires-python` ranges stay open by design (the pin wins discovery; operator declined
bounding). This repo's pin is landed on dev (the fleet-load-bearing one: `uv run --project
<clone>` discovers the interpreter from the project, so this pin governs every wrapper-era
and future `$/`-clone install). The rest are committed but UNPUSHED, one per repo, on each repo's checked-out branch:
logger-conf (update-release-devkit), lbe-toolkit / Make-it-Sing / Nessle / ObserveThing
(ci-support-redux each), infra-github-org / infra-github-runners / infra-rathole / infra
(dev each), prepo (main), pulsar (feature/working) — unity-devkit's landed with the PR #8
merge. `misc` is not a git repo — no pin, no
CI. Secondary finding from the same investigation, unfixed: `ensure_actionlint()` fetches
the upstream checksums file on every run even when the binary is warm-cached — the lint's
one live network dependency (offline-persona hole; zizmor's hashes are constants here) —
and the bootstrap's `curl -fsSL` calls carry no timeouts — a stalled connection hangs
forever, silently. Fix candidates: checksums as repo constants (zizmor pattern) +
`--connect-timeout`/`--max-time` on the two downloads.

Carried risks, unobserved: the unity self-hosted fleet's runner version needs ≥ 2.336.0 for
`$/` (the unity legs execute the install trio on that pool once the consumer-half flip
lands) — the capture-tool pilot surfaces it; Phase 3's landing did not (its unity legs still
raw-checkout). The hosted half is retired:
PR #3's green re-run certified the install trio's first full live pass (`$/`
self-reference resolution from a called reusable works on a current hosted runner).

Ruled out (do not re-propose without new information): an added composite-lint layer
(bettermarks/composite-action-lint surveyed).

## The model: two layers, one seam

The `-devkit` suffix names two different kinds of repos, and every smell the session found was
a piece sitting on the wrong side of the seam. The test is one question: **does this code know
GitHub exists?**

- **Domain toolchains** — unity-devkit, docker-devkit, python-devkit (+ logger-conf,
  openapi-client-codegen, pydantic-settings-pulumi, lbe-toolkit as simple publishers): pure
  "how to build/test/mirror/publish-in-the-abstract X", meaningful from plain bash on a laptop,
  coupled by domain, PyPI-pinned via each consumer's `uv.lock`. Hard law: no ambient `GITHUB_*`
  reads, no `::` annotations, no `$GITHUB_OUTPUT` writes in domain code. Convention: verbs
  print neutral output (JSON leg lists, plain banners); decoration may detect the platform,
  logic never may.
- **The platform binding** — release-devkit renamed **github-actions-toolkit** (plural, matching
  the product): everything that knows GitHub Actions exists. One repo, clone-pinned,
  dependency-of-nothing. Holds: all reusable workflows, the release composite, `lint-workflows`,
  the merge-gate bot, the release/delivery verbs (OIDC trusted publishing, Releases API,
  `GITHUB_REF` parsing are platform-bound), runner provisioning (absorbed `setup.py` +
  vendored `third-party/`), and the matrix helper. Its own `uv.lock` resolves
  `bashrun` + `build-artifact-registry` + pydantic/strictyaml/typer.
- **build-artifact-registry** — ci-devkit's surviving half, renamed to its job: registry
  primitives for pushing/pulling build artifacts, locally or remotely (`builds`, `cache`,
  `setup_oras`, `registry_auth`). Purely registry concerns; no presentation, no runner
  knowledge. ghcr is a registry choice passed as a parameter, not platform coupling.

Supporting laws:

- **Verbs are named for side effects, never execution context.** "ci" is a context; shelf/push
  is a side effect. `ci-build-unity` → `build-unity` with no mode switch (operator ruling,
  2026-10-10: shelving is implied by supplied registry env — the flag was judged noise in the
  verb's CI shape; docker keeps its explicit `--push`); docker's `build --mode ci` →
  `build --push` (image push + digest manifest), with runner provisioning peeled to binding
  pre-steps.
- **Stable-CLI-API doctrine is fleet law**: script names and flags are public API for every
  devkit, not just the binding repo — structure (in github-actions-toolkit) and code (in
  consumer locks) are pinned by different mechanisms, so the YAML's expected verb surface must
  not move silently.
- **Prose rule**: fleet docs retire bare "registry" — "package registry" for the publishing
  side (PyPI/npm/NuGet), "build-artifact registry" for the OCI artifact side. Existing adapter
  names (`NuGetRegistry` etc.) already follow the cargo-qualified pattern; only prose changes.
- **Fleet YAML formatting is retained, not reformed**: blank lines between jobs and top-level
  keys, permissions and secrets as block maps. The migration changes structure, not style.
- **No GitHub merge queues**, permanently: they land merge-group trees, never the certified
  PR head. actionlint stays; reassess only if upstream stalls on `$/`.

## Binding decisions (operator, 2026-10-09 session)

- All reusable workflows (preflight, mirror, update-pr-draft-release, merge-gate, unity
  build/compile-check, docker build) live in github-actions-toolkit. release-devkit is
  renamed github-actions-toolkit. Pinning stays lint-enforced multi-spelling (literal `@<full-
  sha>` at every call site; routers/dispatcher muxes and generated pins were designed and
  rejected).
- release.yml delivery jobs get a devkit-owned **composite action** (trusted publishing binds
  repo + workflow filename; composite steps run inside the caller's job, so `job_workflow_ref`
  keeps naming the consumer's `release.yml` — warehouse#11096 blocks reusable workflows only).
  The per-consumer `setup-release-devkit` wrapper and `RELEASE_DEVKIT_COMMIT` die fleet-wide.
- ci-devkit splits as above; **`ci_step` is killed entirely** — its features are digestion of
  data the platform UI already holds (native step grouping/timing/failure marking, per-line
  timestamps); plain print banners replace it everywhere. ~12 call sites, mechanical.
- Matrix verbs emit **bare leg lists** (no `{'include': …}` envelope, no `matrix=` output
  spelling); the binding composes the GHA envelope and `$GITHUB_OUTPUT` transport via a helper
  verb, which is also the one place to guard the empty-legs case (the `fromJson('')`
  render-time footgun). The leg schema (which keys a leg carries) is named contract.
- `free_disk_space` and friends are runner provisioning owned by the binding layer (reusable
  inputs / pre-steps), not `docker-devkit.yaml` keys.
- Filenames inside the one repo disambiguate: `build-unity.yml` / `build-docker.yml` (job names
  `build-unity` / `build-docker`); `mirror.yml`, `compile-check-unity.yml` as named.
- `publish-compose` stays local in placeframe permanently (one consumer; being redesigned).
- The fleet jumps from diverged state directly to the new shape; there is no intermediate
  re-convergence onto the trim grammar.

## Verified platform mechanics (do not re-derive; researched 2026-10-09)

- **Composition is job-level.** A caller workflow mixes local jobs and `uses:` calls freely;
  `needs` wires across both. A calling job accepts only `needs`, `if`, `permissions`, `with`,
  `secrets`, `strategy`, `concurrency`, `name` — never `steps`, `runs-on`, `container`, `env`.
  Inside the called workflow everything is an ordinary workflow: multi-job graphs, internal
  `needs`, a getter job emitting output consumed by a fanout via
  `strategy.matrix: ${{ fromJson(needs.matrix.outputs.matrix) }}`, `container:` from matrix,
  `fail-fast`.
- **Self-checkout is first-class — but not via `actions/checkout`.** `job.workflow_repository` +
  `job.workflow_sha` give a called workflow its own resolved repo and SHA, and a bare-SHA
  `git fetch --depth 1` serves them on GitHub, hidden `refs/pull/N/merge` tips included
  (allowTipSHA1InWant) — verified live 2026-10-10 against the merge-ref SHA of this repo's PR #3
  failed run. `actions/checkout` cannot make this clone: it refuses any `path` outside
  `$GITHUB_WORKSPACE` (actions/checkout#197, every release since v2), and the toolkit clone must
  live outside the workspace (consumer-checkout's `git clean -ffdx` would wipe a nested copy;
  the consumer's zizmor scans the repo root, respecting .gitignore but not untracked clones).
  github-actions-toolkit's install mechanism is the hand-fetch inside its `toolkit-checkout`
  composite — same shape as its self-test clone, no token (public org).
- **`uses:` is resolved statically by GitHub, server-side.** No expressions, no env, no
  filesystem. Cross-repo refs must be `owner/repo/.github/workflows/file.yml@ref`; `./` refs
  resolve same-repo at the caller's commit — github-actions-toolkit's own `integrate.yml` calls
  its own reusables via `$/` with no SHA and no self-pin bump. Consequence: a consumer's SHA is
  spelled only in the consumer's own files.
- **Same-org self-hosted runners work in called workflows** (callee uses the caller's runner
  pool); the org `unity` runners qualify. `github` context in the callee is the caller's event.
  Caller's `vars` are visible; secrets must be passed per call and forwarded explicitly at
  every nesting hop. `GITHUB_TOKEN` permissions propagate maintain-or-reduce.
- **Outputs chain** through `on.workflow_call.outputs` at each level.
- **Footguns.** `fromJson` on an empty string fails at render time. Nested-call limit is 10
  (this plan uses at most 2). Matrix-derived values interpolated into `run:` lines ride step
  `env` with the run line referencing the variable (zizmor template-injection remediation) —
  the standing law inside every devkit-owned file.
- **The `secrets` context never enters composite-land** (verified 2026-10-10). Withheld from
  action files entirely — a parse failure (`Unrecognized named-value: 'secrets'`), not an empty
  string (github/docs#12705; the VSCode language server enforces the same availability list) —
  and unavailable in `if:` conditions even in workflows. Crossing points: workflow/step `env:`
  and step `with:`, in workflow context only. Consequence: the consumer's release.yml maps
  `NUGET_USER` in workflow-level env; the composite gates the login on `env.NUGET_USER != ''`.
- **Local `uses:` inside a composite resolves against the consumer's workspace**, not the
  action's own checkout (actions/runner#1348) — composite→sibling references are impossible;
  the native fix is the `$/` self-repository reference (in use for the install trio). The
  release composite stays self-contained regardless — the duplicated prelude is the accepted
  price.

## To verify during the pilots (new mechanics, not yet verified)

- PyPI/npm/nuget trusted publishing accepts publishes through composite-wrapped steps
  (expected yes — identity binds to the job's workflow file; warehouse#11096 is about reusable
  workflows). Verified once in the bashrun pilot. **Fallback if rejected**: release.yml keeps
  inline verb steps; the release.yml half of the old verb-grammar lint revives; only the
  wrapper dies.
- `env` context in a composite step's `if:` (the NuGet login's presence gate): listed available
  in the composite context set, but historically buggy on old runners — first live exercise on
  the placeframe pilot leg (Phase 6).

## Phase 3 — unity-devkit (domain purification + renames)

- `ci-build-unity` → `build-unity`, taking no mode switch: shelving (the build-output push plus
  the license/UPM/library CI cache bundle) is implied by supplied registry env; absent registry
  env is the local build (operator ruling — `--shelf` was noise, implied by the verb's CI
  shape); matrix verbs emit bare leg lists (the leg schema —
  `project`, `platform`, `editor-image` — becomes named contract in its AGENTS.md;
  renaming a key breaks the binding's fanout YAML). The `matrix=`/`license=`
  `$GITHUB_OUTPUT` lines die with the bare-list protocol: the binding's getter derives the
  license cache key by calling `unity-license-tag` directly (daily UTC tag, domain grammar), so the
  domain matrix verbs carry zero GitHub output flavor. The consuming flag renames with it:
  `--license` → `--license-cache-key` on `build-unity`/`compile-check-unity` (the value is the
  ORAS tag the license cache restores under, not a license) — one more API break riding the
  `major_minor` bump.
- `--version-code` → `--commit-count`, and the build verb takes over the stamp composition: given
  `--version` (bare base) and `--commit-count` (ordinal), it stamps
  `bundleVersion = {version}+{commit-count}` and `AndroidBundleVersionCode = commit-count` from the
  one input pair — rendering, not deriving (it performs no tag math, computes no count), so
  string and integer cannot disagree; the seam law amends from "stamps verbatim, no composition"
  to "derives neither fact, renders both fields".
- The neutral registry-auth env drops its `CI_` prefix: the verbs read
  `REGISTRY_TOKEN`/`REGISTRY_USERNAME` (matching the binding's docker explicit-parameter
  contract, which always spelled it this way). The reader is build-artifact-registry's
  `registry_auth` chain — that repo takes the matching rename as a small API bump sequenced with
  this phase; unity-devkit's AGENTS.md env contract updates with it.
- Verb option-declaration order in typer mirrors the binding's switch order exactly — project,
  platform, version, pr-number, commit-count, license-cache-key, registry
  (`compile-check-unity`: project, license-cache-key, registry) — so `--help` and the fanout run
  lines read identically top-to-bottom (operator ruling: the order in these workflow files IS
  the order the typer options are declared in).
- Drop `ci_step` and `setup` imports: provisioning (configure_git, disk space, toolchain
  installs) moves to the reusable's pre-steps in github-actions-toolkit; banners replace
  `ci_step`. Verbs assume a provisioned environment.
- `0.2` → `0.3` (`major_minor` bump carries the API breaks), publish dev prerelease.
- AGENTS.md "Consumer CI template" section replaced by the reusable reference; config-file law
  row for unity-devkit unchanged (JSON exception — read by C# inside Unity).

## Phase 4 — docker-devkit

- Absorb the CI shim into the build path with **explicit parameters** (registry, actor, token
  supplied by the binding — no ambient `GITHUB_*` reads in domain code): `build --push`
  replaces `build --mode ci`; deletes placeframe's 53-line `ci/build_docker.py` wrapper;
  capture-tool's workflow-level QEMU/buildx/login steps die the same way (QEMU arm64 stays one
  setup step inside the reusable).
- `docker-build-matrix` learns the cross-compile cohort (`x-cross-compile-targets`,
  platform-pinned services, `platform` facts from manifest `platforms:` keys) and emits bare
  leg lists; capture-tool's `build-docker` stops hand-enumerating targets.
- Drop `ci_step`. `0.2` → `0.3`, publish dev prerelease.

## Phase 6 — pilots

- **bashrun** after Phase 2: exercises preflight + merge-gate + the release composite; carries
  the PyPI-through-composite verification gate (fallback decision point for release.yml).
- **placeframe-capture-tool** after Phases 3–4: exercises mirror + preflight, unity build
  (per-leg base-version stamping), docker build, update-pr-draft-release.

## Phase 7 — fleet sweep (folds ci-refresh-seed; the old doc's mechanics re-aimed from
"wrapper re-pin + grammar rewrite" to "atomic cutover to reusables/composite + SHA bump")

**Registry state (verified 2026-10-08; re-verify anything load-bearing).** Stables: bashrun
0.3.0, ci-devkit 0.2.0 (frozen), docker-devkit 0.2.0, logger-conf 0.2.0,
openapi-client-codegen 0.2.0, python-devkit 0.2.0, unity-devkit 0.1.25,
pydantic-settings-pulumi 0.1.2. Dev prereleases: bashrun `0.5.0.dev37693327146` and ci-devkit
`0.2.1.dev37711169350` (old run-keyed), docker-devkit `0.2.1.dev109`, unity-devkit
`0.2.0.dev215` (count-keyed). npm: `org.outernet.playerbuild` 0.1.5, `org.outernet.lbetoolkit`
1.0.0, `.livekit`/`.photon` at `0.0.0-local` (first new-paradigm publish = 1.0.x). **Poisoned
bases** (run-id prereleases make the base uninstallable): docker-devkit 0.2.1, bashrun 0.5.0,
ci-devkit 0.2.1, pydantic-settings-pulumi 0.2.0 — resolution is the major_minor sweep. **Broken
stables**: docker-devkit 0.2.0 and unity-devkit 0.1.24 pin a nonexistent ci-devkit prerelease —
uninstallable; decision: no yank. PEP 440 `.devN` compares numerically: run-id-keyed floors die
on the first count-keyed publish; Make-it-Sing's exact `docker-devkit==0.2.1.dev37485576216`
already excludes the count-keyed line.

**Bump table (re-derived for the split).** build-artifact-registry: line already at `0.2`
(the registry-auth bump landed; consumers floor at `>=0.2.0.dev0`). bashrun `0.5` → `0.6`
(retires the poisoned never-stable 0.5). python-devkit, docker-devkit, unity-devkit
(+ `org.outernet.playerbuild`), logger-conf, openapi-client-codegen,
pydantic-settings-pulumi: `0.2` → `0.3` (unity/docker rows carry the API breaks; python-devkit
`0.3` is published). placeframe's 8 packages +1 minor each (api-client 0.1→0.2; core/arfoundation/
magicleap 1.0→1.1; auth/logging/common/core-python 0.1→0.2). lbe-toolkit 1.0 → 1.1 (all three
packages). App entries NOT bumped (not registry-consumed).

**Per-repo cutover (atomic per repo):** rewrite `integrate.yml`/`merge-gate.yml` to the
consumer end-state shapes, rewrite `release.yml` to composite calls (fallback grammar if the
pilot rejected composites), bump every `uses:` SHA to one fresh github-actions-toolkit SHA and
relock onto the bumped floors — all in the same commit; old files + old pins stay mutually
consistent until the switch.

**Sequencing laws.** Prereleases must exist on the registry before downstream relocks reference
them; devkit repos merge and are pushed first (pins must exist on the remote before consumer CI
runs); one repo = one PR landing via its own merge-gate; the sweep deliberately does NOT
promote to stable (promotions happen naturally later; green sweep then promote `dev` → `main`
where receivers live on the default branch); update stale agent docs alongside code (instance:
build-artifact-registry's AGENTS.md names the binding repo by its abandoned intermediate
spelling in the release-flow section).

**Sweep order.** Devkit self-cutovers first (build-artifact-registry,
github-actions-toolkit's own files beyond `$/` refs — none needed, python/docker/unity/devkit
repos themselves), then simple publishers (logger-conf, openapi-client-codegen,
pydantic-settings-pulumi, lbe-toolkit), the infra trio (infra-github-org,
infra-github-runners, infra-rathole — preflight + merge-gate only), app repos
(Make-it-Sing, Nessle, ObserveThing, StatefulUnity), placeframe-capture-tool is the Phase 6
pilot, placeframe last (most local surface).

**Per-repo specifics (from reconnaissance; mechanics re-aimed).** placeframe: 8×
`registries:`→`registry:`+`identity:`, drop `ci_workflow:`, `built_images: true` confirmed,
mirror-images precedes preflight (postgres FROM mirror-pinned base), `.github/workflows/
AGENTS.md` documents the OLD contract — prose update is load-bearing, `cesium.yml`
dispatch-only gets signature checks + wrapper-conformant checkouts; its in-flight
`more-ci-fixes` branch (pin→ed406a0) folds or is superseded; placeframe additionally keeps
`get-docker-matrix`-consuming local docker legs until Phase 4's matrix covers them, and
`publish-compose` local permanently. Make-it-Sing: landing strategy ci-support-redux → new
shape → green → merge-gate → evergreen `dev`; `built_images: true` confirmed
(`build-livekit-token`); replace exact docker-devkit pin with `>=` floor; repo-local
`build-livekit-token`/`build-docker` jobs fine. lbe-toolkit: build on ci-support-redux, 1.0→1.1
all three packages, delete legacy `publish-config.json`, npm identities
`org.outernet.lbetoolkit[.livekit|.photon]`, then retire old ci.yml/release.yml.
placeframe-capture-tool: app `builds` dict→list, add `update-pr-draft-release`, adopt new-line
UPM pins (verify consumed set), supersede stale local branches. Infra trio: non-publishing
(integrate + merge-gate only); canonicalize preflight onto `uv run preflight-python` (adds
python-devkit dev-dep, follows python-devkit's new line); infra-github-org owns the
`evergreen-dev` ruleset + merge-bot App + `UNITY_*` wiring; **inspect infra-github-org's tree before committing there — reconnaissance
found `src/stacks/dev.py` locally modified, so re-verify current state**.

**pyproject hygiene, every repo, every in-tree pyproject.** Delete deptry
`known_first_party` self-declarations (instance: placeframe `build/pyproject.toml`;
`per_rule_ignores` tables stay; red windows close at each repo's relock onto python-devkit's
fixed line). Delete `[tool.uv]
prerelease = "if-necessary-or-explicit"` (uv 0.12 deprecates; drop the table when it's the
only key). Delete redundant hatch wheel `include` blocks naming files under `packages`
(instance here: this repo's own `pyproject.toml` wheel includes for `py.typed`/`zizmor.yaml`;
placeframe datamodels uses `force-include` — inspect and drop the same way).

**Standing constraints.** The GitHub App token cannot push or merge — lands go through each
repo's merge-gate or the operator. The agent never runs `git fetch` and never uses prepo in
these repos: branch plainly in the main checkout (`git checkout -b <name>`), treating the
local checkout as the session's state — origin-side truth arrives through the operator.
**Never label a PR in a repo without a live verification
job** (vacuously-true all-green) — lbe-toolkit and Make-it-Sing must not see `ready-to-merge`
before integrate runs.

**Operator-owned prerequisites.** evergreen-dev ruleset membership for Make-it-Sing +
lbe-toolkit; `MERGE_BOT_APP_ID` var + `MERGE_BOT_APP_PRIVATE_KEY` secret per repo; `UNITY_*`
secrets; npm trusted-publisher rows for the three `org.outernet.lbetoolkit*` names bound to
`release.yml`; a per-repo `NUGET_USER` secret for every nuget-publishing consumer (placeframe) —
never org-level, org secrets are fleet-visible and would switch the login on everywhere. The
agent verifies wiring exists before labeling; it does not prepare the
ruleset PR.

**Operator-owned org-level hygiene (threat-model load-bearing, independent of any parked
initiative).** Org-wide push ruleset path-restricting `.github/**` on all branches, bypass =
operator (closes the compromised-member workflow-edit path); fork-approval tier "all external
contributors" on every public repo (fork workflow spellings never auto-run; also rations
hosted-runner slop); org default workflow permissions read-only; "Allow GitHub Actions to
create and approve pull requests" OFF.

## Consumer end-state

Simple publisher (e.g. bashrun) — `integrate.yml` is `preflight` (uses; the script is a
two-line Python file calling `uv run --locked preflight-python` through bashrun) +
`update-pr-draft-release` (uses, `needs:
[preflight]`); `merge-gate.yml` is triggers + concurrency + one gated `uses:` call;
`release.yml` is triggers + concurrency + delivery jobs of one composite `uses:` each — plus,
for nuget-publishing consumers only, one workflow-level env line mapping
`NUGET_USER: ${{ secrets.NUGET_USER }}` (the composite's login gate keys on its presence; see
the secrets-context bullet in verified platform mechanics).

placeframe-capture-tool `integrate.yml` (canonical example — the target spec; formatting is
the established fleet style, which the migration does not change; job key order: `needs`,
`permissions`, `uses`, `with`, `secrets`):

```yaml
name: Integrate

on:
  workflow_dispatch:
  pull_request:
    branches: [dev]

concurrency:
  group: integrate-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  mirror-images:
    permissions:
      contents: read
      packages: write
    uses: outernet-foundation/github-actions-toolkit/.github/workflows/mirror.yml@<sha>

  preflight:
    needs: [mirror-images]
    uses: outernet-foundation/github-actions-toolkit/.github/workflows/preflight.yml@<sha>

  build-unity:
    needs: [preflight]
    permissions:
      contents: read
      packages: write
    uses: outernet-foundation/github-actions-toolkit/.github/workflows/build-unity.yml@<sha>
    secrets:
      unity-email: …
      unity-password: …
      unity-serial: …

  build-docker:
    needs: [preflight]
    permissions:
      contents: read
      packages: write
    uses: outernet-foundation/github-actions-toolkit/.github/workflows/build-docker.yml@<sha>

  update-pr-draft-release:
    needs: [build-unity, build-docker]
    permissions:
      contents: write
      packages: read
    uses: outernet-foundation/github-actions-toolkit/.github/workflows/update-pr-draft-release.yml@<sha>
```

placeframe: same skeleton plus local `build-docker` / `publish-compose` legs (repo-owned
scripts; `build-docker.yml` replaces the getter + wrapper once Phase 4 lands), unity
`compile-check-unity.yml` call, `update-pr-draft-release` needing `publish-compose` + the
unity fanout; its `scripts/preflight.py` carries the DB battery, and the calling job's
`packages: read` supplies the mirrored postgres the battery pulls. What stays local is an
ownership boundary, not a mechanics one: repo-owned scripts (the preflight script itself
included), `publish-compose`.

## lint-workflows disposition

Philosophy carried from the executed trim: found-file model, no presence checks (accepted
hole: renaming a canonical file dodges its contract — self-inflicted, accepted); taste is not
lint; misordering fails loudly at runtime. The single-copy artifacts make most of the old
surface structurally impossible to drift, so the lint shrinks to exactly four things —
actionlint + zizmor + the SHA law + the concurrency model checks:

| Concern | Disposition |
|---|---|
| actionlint + zizmor layers | unchanged; devkit-owned files audited by the devkit's own self-lint; composite internals zizmor-covered at the devkit root, actionlint-blind (composites fail loudly on bad inputs instead) |
| SHA pin law | **the core check**: every `uses:` ref to github-actions-toolkit (workflow or action) is a full 40-hex SHA; all refs to it in one repo carry the same SHA; the canonical repo name is enforced (GitHub's rename redirect must never mask a stale spelling); within-file YAML anchors on the `uses` scalar sanctioned |
| Inline-delivery law | **dropped** — no delivery reusable exists to forbid; violating requires authoring new machinery (a consumer-local reusable or a devkit-grown one), and the failure would surface at delivery time with a confusing OIDC error; cheap insurance judged not worth a check |
| release.yml concurrency | `release-${{ github.ref }}`, no cancel — the delivery mutex: with no group, concurrent dev runs lose sections to the `dev-builds` read-modify-write race; with cancel, a mid-flight publish dies half-done and the cancelled merge's section is permanently lost (per-SHA snapshots are never rewritten) |
| merge-gate wake shape | labeled-only wake, per-PR serializing group — the group closes the real race (two rapid pokes both read OPEN/green/rebased before either merges → double merge); the labeled-only trigger half guards gate availability (dead-gate detection); the workflow_run half is redundant with zizmor's dangerous-triggers audit and rides along free |
| integrate/merge-gate grammar, verb spec tables, ref/tag-fetch laws, verb-installation, env-reference resolution, wrapper validation, one-saver-cache, nuget-key env law + `declares_nuget()`, `environment:` ban | **die** — absorbed by single-copy reusables/composite (cannot drift), already actionlint/zizmor territory, or moot with the wrapper's death |

## Out of scope (recorded, not planned)

- The `$/` flip's consumer half remains parked: consumers' local-job wrappers
  (checkout/setup-uv) flipping to `$/` — the toolkit flipped its own files already (the
  trio composites + the own preflight call, with the actionlint bridge flags standing in
  for rhysd/actionlint#732), and the bridge retires by pin bump once a release accepts the
  spelling; the unity runner fleet's version is the live gate to watch on first exercise.
- Supply-chain initiative — parked at `todo/supply-chain-control.md` (resume after Phase 7
  cutover). Not adopted there: fleet-wide `--min-severity medium`.
- Hotfix release model — parked at `todo/hotfix-release-model.md`.
- Fork-contribution model — parked at `todo/fork-contribution-model.md`.
- Unity license and runner redesign — parked at `todo/unity-license-architecture.md`.
- Path-diff change-detection bug (build inputs outside a package's declared `path` are
  invisible) — parked at `todo/CRITICAL-BUG.md`.
- Any change to release.yml's inline delivery model beyond the composite; any org-level
  workflow mechanism; renaming canonical workflow filenames (npm/nuget publisher bindings
  forbid it).
