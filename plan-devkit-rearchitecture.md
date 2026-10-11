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
sweep, same class as build-artifact-registry's carry below. The Phase 7
sweep follows.
Phase 6 (bashrun leg landed; the capture-tool pilot cancelled by the ruling below): PR #8 (`0.6.x`) open on dev, integrate green — the
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

Resolved — the channel-input redesign (`bdb1e2a`): the boolean was the defect, not the
expressions. `stable: true|false` forced a bool→channel mapping somewhere inside the
composite, and both mapping sites in `${{ }}` are coercion traps (truthiness of stringified
`"false"`; number-cast of stringified `"true"`). The fix deletes the mapping: the composite's
input is now the required string `channel` (no default), consumed in exactly two places —
`persist-credentials: ${{ inputs.channel == 'stable' }}` (string equality, the NuGet login
gate's comparison class, live-green through every bashrun landing) and `RELEASE_CHANNEL:
${{ inputs.channel }}` (pure value forwarding, the class that was live-correct through both
incidents). Ruling amended to accurate form: booleans never cross into expression evaluation
inside a composite; strings may, forwarded as values or compared as strings. Failure matrix:
an omitted input fails at composite input validation before any step; a wrong value dies at
typer's Choice parse (the `ReleaseChannel` enum, verbs/release.py) before any side effect;
`persist-credentials` computes false for anything but the exact `stable` spelling — a garbage
run never holds push creds; `channel: pr` in a delivery job dies at the GITHUB_REF
PR-number parse. Alternatives considered and rejected by operator ruling as ugly: the
two-composites split (the seam-law fundamentalist shape — `release-dev`/`release-stable`,
channel hard-coded per file, caller spelling the choice as the reference) and the prior
session's env+bash-branch draft (aborted then, rejected on re-derivation). Local
verification: lint-workflows green over the modified composite, 157 tests pass. Live-certified
afterward on both channels: the landing's dev job ran dev, the re-promotion's stable job ran
stable — each boolean-era failure exercised in its corrected direction.

Recovery executed green, end to end: PR #10 (`toolkit-channel-input`: repin to `8ac57f2`,
both delivery jobs' `with:` flipped to `channel: dev`/`channel: stable`, `major_minor`
0.7 → 0.8 riding the same landing) merged as `e9692f3`; the landing's dev channel published
`bashrun 0.8.0.dev85` — the dev job running dev, the corrected direction of the 0.6.0-orphan
failure; the operator re-promoted `dev:main` (fast-forward, main = dev = `e9692f3`) and the
stable channel ran its first correct pass — published `bashrun 0.8.0` to PyPI, tagged
`bashrun-v0.8.0`, cut CalVer `2026.10.5` (no `.4` exists — the failed promotion cut nothing),
reset `dev-builds` — the stable job running stable, the corrected direction of the promotion
failure. Re-running 38107631822 was useless and was not attempted: a rerun re-executes the
composite at the SHA cc809cb's release.yml pins (the broken v2), and release.yml has no
workflow_dispatch trigger. Pilot state closed: preflight and the gate reusable certified on
three landings (PRs #8, #9, #10); the release composite certified on both channels
(`0.8.0.dev85` and `0.8.0` live on PyPI); trusted publishing through composite-wrapped steps
verified on both channels — the inline-verb fallback is dead; the first-ever promotion and
stable pass landed green; the stray `0.6.0` orphan stays by ruling. bashrun's local clone lags
origin (checked out on `toolkit-channel-input`, dev ref at `cc809cb`) — the operator pulls
before the next session touches it.

Operator rulings (2026-10-11 session): the capture-tool pilot is CANCELLED — Phase 7 runs as a
straight DAG sweep, and the reusables no landing has exercised in consumer shape (mirror, the
unity/docker build reusables, the per-leg stamping path) certify live at their first swept
consumers instead; the unity runner ≥ 2.336.0 gate moves with them (unity-devkit's own
self-cutover is the first unity-legged cutover on that pool). And every repo goes all the way
to main during the sweep: land on dev (its own gate, or operator push for a repo's own
landing), promote dev → main (fast-forward, operator-owned), let the stable channel publish the
new line — the "sweep deliberately does NOT promote" law is dead. Each repo relocks onto the
latest published versions of every dependency at its cutover: stable spellings once the
upstream has promoted, dev prereleases before that; floors may keep the `>=X.Y.Z.dev0`
spelling. The sweep's first two nodes: build-artifact-registry LANDED end to end (self-cutover
at toolkit `66df38b`, wrapper action deleted, config migrated to `registry:`+`identity:`,
sidecar relocked onto the python-devkit 0.3 line, deptry self-declaration deleted, main lock
refreshed to bashrun 0.8 — merged through its gate, promoted dev → main, and stable
`build-artifact-registry 0.2.0` published to PyPI: the identity's first stable, so the publish
needed no major_minor forcing — no tag ever existed under the new name; the 3.15 wrapper carry
died with the wrapper). python-devkit's self-cutover is handed off on branch `toolkit-cutover`
(off the phase-5 tip `c8efa62` — local dev predates Phase 5; same consumer shape at `66df38b`,
wrapper deleted, config migrated, harness `scripts/preflight.py` running the verb itself — the
self-preflight exception, no sidecar, no dependency — hatch wheel `include` block dropped,
relock onto bashrun 0.8/pydantic 2.14/typer 0.27.3; battery, lint-workflows, and
validate-release-plan all green locally). Remote toolkit dev verified at `66df38b` (App token);
the plan-record commits ride local until the operator pushes.

Session records (2026-10-11, docker/unity node pair): the toolkit briefly grew an
`execute-method` call input on `compile-check-unity.yml` for unity-devkit's self-consumption —
the operator design-review rejected it (per-project facts belong in the per-project config or
nowhere), and the ruling went further after inspecting what the self-test was:
`EnvironmentFixtureSelfTest` (the harness's one executed C# test — a dress rehearsal of
PlayerBuild's environment materialization against a fixture asset, asserting outcomes a real
build never checks) is EXPUNGED entirely, operator ruling, with every trace: `Assets/Editor/`
(FixtureEnv.cs, the preset asset, the driver), the dead `tests/fixtures/environment-dump.json`,
and — because their only caller died — the `--execute-method`/`--build-target` flags on
`compile-check-unity` itself (the method-driver mode had zero fleet users; `PLAYERBUILD_ENTRY`
hard-coded in the build verb is the only executeMethod the fleet needs). The compile gate is
compile-only everywhere now, uniform by construction. Accepted risk, on the record: the
reflection-driven materialization failure mode (compiles green, silently misapplies settings,
surfaces as mysterious consumer builds) has NO detector in the fleet; the operator chose
uniformity over the smoke test. Both nodes cut over on the plain reusable set at `66df38b`
(unity-devkit: workflow files, wrapper + actionlint.yaml deleted, scripts/preflight.py,
hatch include hygiene, relock onto bashrun 0.8/bar 0.2.0/python-devkit 0.3.0 all stable;
docker-devkit: same shape, plus one real lint fix — ruff 0.17's unconventional-import-alias
wanted `datetime as dt` in image_refs.py). Both verified locally: battery, lint-workflows,
validate-release-plan. unity-devkit branched off the phase-3 tip `d7c2324` (`toolkit-cutover` @
`fafd95f`), docker-devkit off the phase-4 tip `820915a` (@ `f56e81c`); local devs lag. Session
closed at the handoff: merges, promotions, and the toolkit push are operator-owned and in flight
(toolkit dev carries three unpushed plan-record commits: `e452d43`, `7cb2702`, `0db597e`). bar
`0.2.0` and python-devkit `0.3.0` stables are already registry-confirmed (both resolved from
PyPI in this session's relocks). Next session opens by closing the devkit tier: confirm
docker-devkit `0.3.0` and unity-devkit `0.3.0` + `org.outernet.playerbuild 0.3.0` live on their
registries, mains promoted, and unity-devkit's integrate green — its compile legs are the
fleet's first `$/` exercise on the self-hosted unity pool, so the runner ≥ 2.336.0 gate's
verdict lands there (a red is a runner upgrade, not a repo fix); pull every touched clone first
(unity-devkit's and docker-devkit's local `dev`/`main` lag their phase tips; bashrun's clone
sits on `toolkit-channel-input`). Then proceed to the simple-publisher tier — logger-conf,
openapi-client-codegen, pydantic-settings-pulumi, lbe-toolkit — every upstream now stable, so
the tier relocks onto stables throughout; lbe-toolkit's operator prerequisites (npm
trusted-publisher rows for the three `org.outernet.lbetoolkit*` names, evergreen-dev
membership, merge-bot wiring) must be verified present before its PR is labeled.

Session record (2026-10-11, devkit-tier close-out): docker-devkit verified done end to end
(main promoted — main = dev, stable `docker-devkit 0.3.0` live on PyPI). unity-devkit's cutover
PR #9 landed through its gate and the dev channel published `unity-devkit 0.3.0.dev227`, but the
repo was never promoted (main sits 20 behind dev — operator step outstanding), and
`org.outernet.playerbuild` published nothing on any channel. Diagnosis: playerbuild's declared
path (`packages/unity/PlayerBuild/Assets/Package`) is unchanged since `playerbuild-v0.1.5` —
phase 3 touched only the python verbs, the expunged self-test lived under `Assets/Editor`
(outside the package path), and the `major_minor: "0.3"` bump rides the root config, which no
package path covers — so pure path-diff gating skipped it. The same correlation hid the gap
everywhere else: python packages always shipped on bump commits because those commits also
touched the python package (the repo's payload). Operator doctrine ruling: a major_minor bump is
itself a release — `compute_release_plan` now forces `publish` when a package's declared line
sits above every existing tag; within the tagged line, patch flow stays path-diff-gated; apps
keep their own any-package-published rule. The clause flows unchanged through every channel and
`validate-release-plan` (159 tests, ruff, basedpyright green). Consequence: unity-devkit's
promotion must repin its toolkit `uses:` past the fix SHA for playerbuild's `0.3.0` to ride the
stable channel — its current pin `66df38b` computes the old gate; npm stays at `0.1.5` until
then.

Session close (2026-10-11): the devkit tier is CLOSED — every devkit landed, promoted, and
stable-published. docker-devkit verified end to end (main = dev, `docker-devkit 0.3.0` on
PyPI). unity-devkit end to end: the repin PR #10 (`toolkit-repin`, toolkit `63b580f`) landed
through its gate, the dev landing published `unity-devkit 0.3.0.dev229` and
`org.outernet.playerbuild 0.3.0-dev.229` — the forced-publish clause's first live exercise
(dev channel, unchanged path, new line) — the operator promoted, and the stable channel
published `unity-devkit 0.3.0` (PyPI) and `org.outernet.playerbuild 0.3.0` (npm `latest`),
pushing both `*-v0.3.0` tags — the clause's second live exercise, stable direction.
python-devkit's cutover confirmed landed (its remote dev's integrate references the toolkit
reusables; main = dev). The npm-silence bug was observed live in the stable run's log — the
publish invisible between `Installing Node.js 24` and post-cleanup — fixed after diagnosis
(`833a74d`, prints the captured npm stdout; consumers inherit it by repinning past it, which
the sweep's fresh-SHA law carries atomically). Residue: unity-devkit carries a closed-unmerged
PR #11 (`0.4.x`) — operator experiment, nothing landed, branch may linger. Resumption: the
operator pushes toolkit dev (`9bca9a2` sweep reorder + `833a74d` npm output were unpushed at
close), then the simple-publisher tier opens — logger-conf first (consumers: placeframe-common
`logger-conf[otlp]`, capture-tool transitively, pulsar scripts), then openapi-client-codegen,
pydantic-settings-pulumi — correction, same session's later ruling: lbe-toolkit moved out of
the tier to sit beside Make-it-Sing, both after placeframe and placeframe-capture-tool (the
sweep-order paragraph carries the amended sequence); then Nessle, ObserveThing,
StatefulUnity last.

Session record (2026-10-11, simple-publisher tier): sweep order amended by operator
ruling (both order statements above corrected in place) — the tier ran as logger-conf,
openapi-client-codegen, and pydantic-settings-pulumi in parallel; lbe-toolkit moved to sit
beside Make-it-Sing, both after placeframe and placeframe-capture-tool. All three repos
carry the cutover on local branch `toolkit-cutover` at toolkit `c1f000c` (remote dev
verified at that SHA via the App token before any repin; the plan-record commits ride
local until the operator pushes): workflows rewritten to the bashrun shape (preflight +
update-pr-draft-release `uses:` calls, labeled-only merge-gate, two composite delivery
jobs channel-spelled), the setup-release-devkit wrapper deleted, `scripts/preflight.py`
sidecars added (`uv run --locked preflight-python` — python-devkit lives in each dev
group, so no bashrun-style `tools/devkit` install sidecar), configs migrated
`registries:`-map → `registry:`+`identity:` with `ci_workflow:` dropped, `major_minor`
bumped to `0.3` everywhere (pydantic-settings-pulumi from `0.1`, skipping its poisoned
0.2 line), redundant hatch wheel `include` blocks dropped (openapi-client-codegen's wheel
verified to still ship `py.typed` plus all 10 `_data` files — a stale pre-committed 0.1.0
wheel in its `dist/` initially masked the check), and relocks onto stables: bashrun
`0.8.0`, python-devkit `0.3.0`, ruff `0.17.0`, typer `0.27.3`, pydantic `2.14.0`/pulumi
`3.268.0` where consumed — ci-devkit dissolved out of every lock, live-confirmed again.
All three batteries green on the first pass (ruff 0.17 flagged nothing here;
docker-devkit's unconventional-import-alias hit did not recur), and lint-workflows +
validate-release-plan green against the toolkit clone in every repo. logger-conf's branch
folds its unpushed `.python-version` commit; the other two repos' pins were already
committed on their checked-out branches. Handoff: pushes, PRs, labels, merges, and the
dev → main promotions are operator-owned (the existing MERGE_BOT/evergreen-dev wiring
carries over unchanged — the old wrapper merge-gate already used the same vars/secrets);
each stable channel then publishes the 0.3.0 line, the forced-publish clause's cleanest
case (the cutover commits touch the package path directly, so path-diff agrees). Same
session amendment: pydantic-settings-pulumi's remote dev had moved past the stale local
ref (two wrapper-era commits — `e97d197` major_minor to 0.2, `8151cab` wrapper repin; the
operator's fetch had already updated `origin/dev`), and its branch is rebased onto
`8151cab` (`3e72865` code + `27d8a41` prose): the base commit `f27ad17` was skipped, not
reconciled (its repin is superseded by `8151cab`, its publish-prerelease rename deleted by
the cutover), and the config keeps `0.3` over dev's `0.2` — the bump table's line, 0.2.0
being the poisoned base the sweep exists to retire. Battery, lint-workflows, and
validate-release-plan re-ran green at the rebased SHA; the operator had already pushed
the pre-rebase branch (`origin/toolkit-cutover` = `925e8c2`), so the rebase lands as a
force push — operator-owned like every push.

Simple-publisher tier CLOSED (operator-confirmed, registry-verified 2026-10-11): all
three repos landed through their gates (the pydantic-settings-pulumi rebase force-push
included), promoted dev → main, and stable-published — `logger-conf 0.3.0`,
`openapi-client-codegen 0.3.0`, `pydantic-settings-pulumi 0.3.0` live on PyPI, each with
its dev prerelease beneath it (`0.3.0.dev54` / `.dev80` / `.dev35`; upload timestamps
~05:14 UTC — the dev-landing-then-stable-promotion sequence, both directions green).
Verification note for future sessions: the unversioned `/pypi/<pkg>/json` endpoint served
stale CDN cache that briefly showed no 0.3 line at all — confirm load-bearing registry
facts on the version-scoped endpoint, which returned fresh data. The operator closes the
session here; toolkit dev carries unpushed plan-record commits (push before consumer CI needs
nothing from them — consumers pin `c1f000c`). Next session:
placeframe first, then placeframe-capture-tool (order load-bearing — capture-tool
consumes placeframe's UPM packages, so placeframe's new line must exist on the registry
before capture-tool relocks onto it); pull both clones before touching them (their local
devs lag their phase tips); the per-repo specifics paragraph carries both inventories
(placeframe: 8× `registries:`→`registry:`+`identity:`, drop `ci_workflow`, mirror-images
precedes preflight, `.github/workflows/AGENTS.md` prose update load-bearing, `cesium.yml`
dispatch-only signature checks, `publish-compose` stays local permanently, DB battery in
its preflight script with `packages: read`; capture-tool: `builds` dict→list,
`update-pr-draft-release` adoption, new-line UPM pins, supersede stale local branches;
bump table: placeframe's 8 packages +1 minor each).

Session record (2026-10-11, placeframe node): the cutover rides local branch `toolkit-cutover`,
nine reviewable commits on `origin/dev` — a design-doc prose commit, the CI-script port
off ci-devkit with the devkit-stables relock, a formatting-only commit for the ported
scripts, the workflow cutover pinning the toolkit tip, the agent-docs prose update, the
openapi-client-codegen relock (below), the canonical `Run generate-clients` regen, and the
cesium.yml deletion (obsolete workflow, operator ruling) with its doc trim. Verified green locally: battery pieces (ruff, format, basedpyright,
pytest, the full DB preflight with docker postgres, `generate-clients --check` api-scope),
lint-workflows, validate-release-plan — the last two against the toolkit clone. The config split `placeframe-api-client` into TWO entries on
one path — `placeframe-api-client` (nuget) + `placeframe-api-client-npm` (npm
`org.outernet.placeframe.apiclient`, fresh tag line) — the one-package-one-ecosystem law
against the old dual-`registries:` map; both lines move together because they share the
path, `placeframe-core`'s sentinel edge on the npm identity resolves through the new entry,
and all 9 entries publish at cutover (forced-publish for bumped lines, tag-None for never-
published). ci-devkit is DISSOLVED out of placeframe entirely: `ci_step` banners became
plain prints in preflight/publish-compose/cesium, cache/setup_oras moved to
build-artifact-registry, the cesium pipeline ported to unity-devkit 0.3's
`restore_or_activate_license(registry, tag)` (the pre-0.1.21 `restore_license()` was long
dead — cesium codegen/combine were already broken at runtime under the old 0.1.25 lock).
cesium.yml itself is DELETED by operator ruling (obsolete workflow): its in-flight typo
fixes, provisioning pre-steps, and SHA-pinning were expunged with the file; the cesium
scripts remain in the tree without an invoking workflow. The datamodels staleness gate keeps
its whole-package pathspec — operator ruling (2026-10-11): staleness checks are never run on
a dirty worktree, so a red from uncommitted hand-owned files is an invocation error, not a
gate defect; the earlier `src/` scoping was dropped, and the recorded concern about
openapi-client-codegen's `--check` covering the whole generated root dissolves under the
same ruling. The relock: bashrun 0.8.0,
build-artifact-registry 0.2.0 (new dep), docker-devkit 0.3.0, unity-devkit 0.3.0,
python-devkit 0.3.0, openapi-client-codegen 0.3.0, logger-conf 0.3.0, typer 0.27.3,
pydantic 2.14.0 — and ruff HELD at 0.14.14 (see below). placeframe's `.python-version`
3.13 pin was already landed. Residue: placeframe's origin remote spells `plerion.git`
(redirects cover it; rename housekeeping host-side, same class as build-artifact-registry's
ci-devkit URL carry).

Toolkit fix riding this node: NONE — the openapi-generator python template's shipped CI workflow
(`python.yml` inside every generated client, unpinned template actions) tripped lint-workflows
24-high at placeframe, and the answer landed at the source instead of a shared-config carve:
openapi-client-codegen now suppresses the template's whole inert-CI class at generation (see
the retirement record below), so the shared zizmor config carries no python.yml ignores and
never did on a pushed tip. placeframe pins the pushed toolkit dev tip — the operator pushes
toolkit dev BEFORE placeframe's PR runs CI; the sweep's fresh-SHA
law carries it to later consumers atomically.

The ruff 0.17 blocker (first live hit; will recur at every remaining node): ruff 0.17 +
the canonical config's `preview = true` surface 51 findings at placeframe — ~40 are
mechanical (RUF105 converts every `# noqa:` to the new `# ruff: ignore` syntax; RUF069
float-equality in tests; RUF201 selector syntax in local layers; ICN001 `datetime as dt`
in GENERATED datamodels), but ASYNC119 flags the Litestar DI idiom
(`async with session.begin(): yield session` ×3) with no honest local fix, and PLW0717
flags the sanctioned long-loop-boundary shape (reconstructor main loop, 15 statements).
The canonical is the single door for fleet lint triage, so python-devkit dev carries the
triage (`9945222`, unpushed): ASYNC119 + PLW0717 join the "Temporarily ignored (will
enable when conventions are established)" block with rationale. Until python-devkit
publishes that line, a consumer cannot both take ruff 0.17 and stay green (sync-ruff
--check compares the committed ruff.base.toml against the LOCKED python-devkit's
canonical) — so placeframe's cutover lock holds ruff at 0.14.14 with everything else on
stables, and the 0.17 wave (canonical re-sync + relock + the ~40 mechanical fixes +
ruff.toml ICN001 generated exclusion, all diagnosed and reverted cleanly here) rides each
repo's next relock once python-devkit ships. Note for that wave: ruff 0.17's stricter
noqa parser also warns on the org-mandated `# noqa-wrapper:` header comment (warning
only, not a finding), and RUF105's autofix syntax (`# ruff: ignore`) is UNREADABLE by
ruff 0.14 — the conversions must land in the same commit as the 0.17 lock bump, never
before. Operator sequencing for this node: push toolkit dev first, then placeframe PR →
label → merge → promote (stable publishes the 0.2/1.1 lines — npm stays put until then);
python-devkit's `9945222` lands on its own schedule but blocks every ruff-0.17 relock
after it. Verify before labeling: `NUGET_USER` exists as a per-repo placeframe secret
(the old workflows-AGENTS prose called it an org secret — if it is org-level, re-create
per-repo and delete the org one; the login must not switch on fleet-wide) and the usual
MERGE_BOT/evergreen-dev wiring. The dev channel's first run will publish dev prereleases
of all nine entries, including `placeframe-api-client-npm`'s fresh line — npm
trusted-publisher rows for `org.outernet.placeframe.apiclient` already exist (it
published under the old single-entry flow); the filename binding (`release.yml`) is
unchanged.

Session record (2026-10-11, generated-CI-baggage retirement): openapi-client-codegen `0.3.1`
published (branch `suppress-python-template-workflow`, `5e1deeb`) — the shipped
`openapi-generator-ignore` gained `**/python.yml`, `**/.travis.yml`, `**/.gitlab-ci.yml`
(the template's whole inert-CI class; placeframe's committed trees carried all three).
Standing discovery, verified A/B against the live generator (7.22.0): anchored patterns
(slash-containing, root-relative, e.g. `.github/workflows/python.yml`) do NOT match in
openapi-generator's ignore implementation — only slash-free/`**`-prefixed globals do, which
is why the pre-existing `.gitignore` entries work; the file's comment records it. Empirical
verification harness note: `uvx --from <local-path>` serves a stale cached env through
`--refresh-package` and `uv cache clean <pkg>` — only outer `--no-cache` forces the rebuild.
placeframe rode two commits on `toolkit-cutover`: the relock onto 0.3.1 (with lock-python
convergence of the per-service pylocks, which had lagged the cutover relock) and the
canonical `Run generate-clients` (9 deletions, 3 FILES manifests, csharp byte-identical;
specs unchanged so `--no-cache` was required past the short-circuit; `--check` green on the
committed tree, ruff/format clean). Certified by lint-workflows green over BOTH trees — the
toolkit's own and placeframe's (via `uv run --project <toolkit> lint-workflows`, cwd
placeframe) — plus validate-release-plan exit 0 and the toolkit battery (160 tests); the
shared zizmor config stays carve-free (`rules: {}`), and no consumer tree carries template
CI baggage. Both local stacks were then rebased for review onto their origin/dev tips
(backups under `backup-pre-review-rebase`): the toolkit's six plan-record commits squashed
to one prose commit with the carve add/retire pair expunged net-zero, placeframe's obviated
pin-bump/doc-rename/repin commits dropped with the cutover commit pinning the rebased
toolkit tip directly. Operator: push toolkit dev (one commit) before placeframe's PR runs
CI, then placeframe's PR carries the nine-commit series.

Session close (2026-10-11): operator adjustments were in flight at this close; they landed as
the next session's consolidation commits, and the record below carries the current tips. As
of this close: toolkit
dev = two prose commits ahead of origin/dev; placeframe's `uses:` pins and cutover commit
message spell `5e7212f`, which stays valid once dev is pushed (an ancestor of the tip,
prose-only delta — repin only if wanted). placeframe `toolkit-cutover` carries the nine-commit
series on origin/dev, worktree clean; the operator owns further reshaping, then the sequence
is: push toolkit dev first, push the branch, open the PR, let CI certify, verify the
per-repo `NUGET_USER` secret and MERGE_BOT/evergreen-dev wiring before labeling. Backups:
`backup-pre-review-rebase` in both repos, `backup-pre-cesium-drop` in placeframe (`84beb852`);
placeframe's `even-more-ci-fixes` (`fb188cd5`) is redundant residue. Verification state: ruff,
format, lint-workflows, and validate-release-plan green at the cesium-drop shape; the
pathspec-drop replay was verified by tree-diff (exactly one line) plus ruff on the touched
file — re-run the full pair at the operator's final shape before labeling. Sandbox note:
placeframe's lock requires uv 0.12.15, and the sandbox default `uv` (0.11.14 at
/usr/local/bin) shadows the host-shared 0.12.15 at `~/.local/bin` — prefix commands with
`PATH="$HOME/.local/bin:$PATH"` (shell exports do not persist between tool calls; child
`uv run` invocations inherit the inline prefix).

Session record (2026-10-11, placeframe script-tier consolidation, operator-ruled): three
commits ride `toolkit-cutover` past the review-rebased tip — `b433a7a2` (delete cesium +
protect-branches), `646757d0` (dissolve build-scripts, inline the preflight, relock),
`40b8aa43` (docs). Rulings executed: the cesium scripts are DELETED, superseding the
placeframe node's "remain in the tree without an invoking workflow"; `protect_branches.py`
and `.github/branch-protection.json` die with them (obsoleted by infra-github-org —
placeframe's census line already carries the full evergreen ruleset triple, the legacy
found-state params `main_ruleset`/`dev_protection`/`merge_only` appear nowhere in dev.py,
and the JSON's required checks were pre-cutover check names under the dead
ruleset-level-check doctrine besides; repo.py's dead params + TODOs are infra-side residue).
The `build-scripts` workspace member is DISSOLVED into `scripts/`: the repo preflight is
inlined into `scripts/preflight.py` (python battery via bash, then image
refs/couplings/DB/datamodels in-process, then generate-clients --check; the `preflight`
entry point and its typer wrapper die — operators run the exact sidecar CI runs),
`publish_compose`/`generate_datamodels`/`sqlacodegen_generator` moved flat into
`scripts/src/scripts/` (entry-point names unchanged, so no workflow YAML changed;
publish_compose's one typer.Option default converted to Annotated, killing the B008 layer
build/ruff.toml carried — the file dies with the dir), root pyproject surgery (member, dev
group, uv.sources, basedpyright include, pytest testpaths), deptry DEP002 ignores carried,
`unity-devkit`/`build-artifact-registry` deps dropped as cesium-only (bar stays resolvable
as docker-devkit's transitive). The split's documented rationale was void all along — one
shared workspace venv, and preflight-python syncs `--all-packages`, so the calibration stack
was in every CI venv regardless. Layout stays FLAT by operator acceptance (no subdirs;
preflight.py pinned at scripts/ root by the toolkit contract). Verified green at the final
shape: ruff/format/basedpyright/pytest, lint-workflows + validate-release-plan against the
toolkit clone, and the sidecar END TO END — preflight-python battery, DB bring-up +
migrations, datamodels staleness, and the FULL generate-clients --check (all specs and
clients, one better than the prior session's api-scope run). The relock diff is pure member
surgery (build-scripts package block removed, dep declarations absorbed under scripts; zero
version churn; per-service pylocks unchanged, lock-python re-run confirmed). Sandbox fact:
after editing a workspace member's entry points, `uv sync` does NOT regenerate stale
console-script wrappers when the member's version is unchanged — `uv sync
--reinstall-package scripts` materialized them; fresh CI installs cannot hit this (wrappers
are written at first install). The two Dockerfile comments naming
`build_scripts.placeframe.context_sha` were corrected to `docker_devkit.context_sha` (stale
before this session — that module lives in docker-devkit).

Session close (2026-10-11, consolidation): placeframe `toolkit-cutover` = `40b8aa43`, twelve
commits on origin/dev, worktree clean; toolkit dev = three prose commits ahead (`7701c06`,
`0ab1fc6`, `c5e49c1`). The full verification pair re-ran green at this final shape — ruff,
format, basedpyright, pytest, lint-workflows, validate-release-plan, plus the sidecar end to
end — so the prior close's re-run-before-labeling demand is satisfied. Operator sequence
unchanged: push toolkit dev first, push the branch, open the PR, let CI certify, verify the
per-repo `NUGET_USER` secret and MERGE_BOT/evergreen-dev wiring before labeling. Backups
unchanged (`backup-pre-review-rebase` in both repos, `backup-pre-cesium-drop` in placeframe);
placeframe's `even-more-ci-fixes` remains redundant residue.

Session record (2026-10-11, review restructure + oras fix): placeframe's branch was restructured
for review — twelve commits to nine, tree-identical to `40b8aa43` (empty tree-diff proof, so the
prior session's verification carries): the formatting fixup squashed into the port, the dead
port-work expunged (the cesium trio and the `ci/preflight` port — deleted or absorbed by later
commits, so the port carries only `publish_compose` + the stables relock and is retitled), the
cesium doc-section add-then-delete pair collapsed into the agent-docs commit (its own commit
dropped), the two cesium deletion commits merged into one pure-deletion commit, and the dead
build-doc updates expunged from the docs commit; kept the relock chain, the `build/pyproject`
dep evolution (each commit's lock coherence), and the root-`AGENTS.md` paragraph evolutions
(true intermediates, not dead content). The operator pushed and opened PR #136; every job green
except `update-pr-draft-release`, dead in 16s at `FileNotFoundError: 'oras'` —
`pull_digest_manifest` (placeframe is the first `built_images: true` consumer of the pr channel)
shells out to an oras binary nothing provisions: the reusable carries no ORAS step and the verb
never installed it. Historical forensics (standing): the pr-draft job has NEVER run green
anywhere — capture-tool's wrapper-era `update-release-devkit` branch (commits `31a929d`/
`3007796`, Oct 6, never merged; residue to supersede at its cutover) failed three runs with the
identical traceback, and bashrun's pilot green run never entered the oras path (no apps, no
`built_images`) — the cancelled-pilot exposure ("reusables certify at their first swept
consumers") fired here exactly as accepted. Nothing was lost; it was never there: every other
oras-consuming verb in the fleet self-provisions in Python at point-of-use (docker-devkit
`push_image_digests` — `bdaf6c6`, the "oras provisioning fix" prerelease capture-tool repinned
at `043a726` — unity-devkit compile-check/build/install), and the release verb was the one
without. Ruling executed, same pattern and NOT a YAML step: toolkit `5376786` "Provision oras
before shelf pulls in the release verb" (`install_oras()` at the top of `stage_apps` and
`pull_digest_manifest`; battery green; operator pushed; remote dev verified at that SHA).
Placeframe repinned all 8 `uses:` refs `5e7212f` → `5376786`, squashed into the cutover commit
(`4b8f08dc`, message respelled; the six later commits replayed; tree-delta exactly the pin
lines; lint-workflows green) — tip `f6ad40bf`, backups `backup-pre-review-rebase-2` (=
`40b8aa43`) and `backup-pre-repin` (= `86023cb8`). The operator force-pushed and the rerun went
green end to end — the oras fix and the shard merge's first live exercise (a SHA's docker-leg
shards enumerated and merged at pull time) both certified; the `pr-136` draft's content rode the
green run. Residue, deferred by operator ruling: the draft release's FORMATTING is not what the
operator intended — the discussion opens the NEXT session as its first item, before any landing
step; the placeframe sequence then resumes where it stands (verify the per-repo `NUGET_USER`
secret and MERGE_BOT/evergreen-dev wiring before labeling; the ruff-0.17/python-devkit
`9945222` blocker unchanged). Toolkit dev carries this plan-record commit unpushed.

Session record (2026-10-11, draft-release rendering redesign — the deferred formatting
discussion, resolved before any landing step): the pr-136 draft's defects were diagnosed
against live data (the actual digest manifest pulled from the shelf for PR #136's head
`f6ad40bf`, the packages API, and browser probes). Findings: the historical
`github.com/orgs/{org}/packages/container/...` package-page URL 500s even authenticated —
the browsable form is repo-scoped `github.com/{repo}/pkgs/container/{name}`; per-version
pages exist and ARE constructible — `…/{version-id}?tag={tag}`, the numeric id from the
packages API versions endpoint matched by digest (verified live for all 17 placeframe
images, every constructed URL 200 anonymous); the "Image" column showed bake target keys,
not image names (`create-database` links package `database-manager`); row order was shard-
hash order (arbitrary to the reader); and the digest column was both the width bomb
(71-char unbreakable token — release bodies CLIP overflowing tables, no scrollbar) and
information nothing on the page consumes. Converged rendering, operator-ruled: tables
everywhere (uniformity), but the digest is never a column; sections open
`### Commit [{sha}](commit-url)` — stable included, which previously carried no commit
line at all; Packages is `Package | Registry | Version` with the version linked to its
registry page; Apps is `App | Platform | Version` with the version linked to the asset
(the platform column is the run-up-to multi-platform apps; `stage_apps` now threads
`artifact.platform`, already config-modeled); Built images is `Image | Tag` — display name
= ref tail under `ghcr.io/{repository}/` (foreign namespace a loud error), alphabetical by
ref, the `tree-` tag linked to that exact package version's page, digest-matched id with
the bare package page as fallback (API blip → degraded link, never a dead run). Landed in
`release.py` + tests (162 green, ruff/format/basedpyright); consumers inherit by repinning
past the SHA per the fresh-SHA law — placeframe's pending repin carries it.

Session record (2026-10-11, release-verb polish and the c093cfb certification): three toolkit
dev commits on top of the rendering redesign. `e34070a` confined release.py comments to short
in-body imperatives inside functions; `9d23aef` inlined the toolchain installs into
`publish_packages` (dotnet/npm provisioning as commented blocks inside the phase; the
provisioning-touching unit tests switched their fake packages npm→pypi so they exercise the
publish loop, never the install code); `c093cfb` aggressively inlined the single-call helpers
into `main` (`create_or_update_release`, `configure_git`, `tree_tag`, `image_display_name`,
`package_version_url` folded in; `publish_packages`/`stage_apps`/`pull_digest_manifest` stay as
phases by operator ruling; `package_version_id` stays per the try-block exception) — which
surfaced a latent bug: the images comprehension's `(tag := tree_tag(entry))` walrus rebound the
enclosing release tag, so any PR/dev run with `built_images: true` would `gh release edit` at
the last image's tree- tag; the inlined loop's distinct `image_tag` fixes it (no test covered
the edit command on that path). Operator pushed toolkit dev = `c093cfb`. Placeframe repinned all
8 `uses:` refs `5376786` → `c093cfb`, squashed into the cutover commit by operator ruling over
the upstream-target convention (fixup + autosquash onto the already-pushed `4b8f08dc`, message
respelled "…at c093cfb", the six later commits replayed via a detach/cherry-pick rebuild after
the post-rebase amend landed on the tip instead of the squashed commit; final tree verified
pin-lines-only) — tip `895b65ee`, operator force-pushed, CI green end to end, and the operator
confirms the `pr-136` draft renders as intended: the rendering redesign's live certification,
closing the formatting loop the review-restructure record deferred. Landing sequence unchanged
(verify `NUGET_USER` + MERGE_BOT/evergreen-dev wiring before labeling; the
ruff-0.17/python-devkit `9945222` blocker unchanged). Next session opens at the
placeframe-capture-tool cutover (Phase 7 sweep; per-repo specifics above: builds dict→list,
`update-pr-draft-release`, new-line UPM pins, supersede stale local branches). Toolkit dev
carries this plan-record commit unpushed.

Session record (2026-10-11, cross-org readiness + binding hardening — Phase 8 authored, no
code landed): investigation across github-actions-toolkit and infra-github-org asked one
question — how far the CI system (evergreen included) is from serving a distinct org
(StatefulUnity today; Nessle and ObserveThing destined to join it; politically separate,
umbrella-adjacent). Findings: the binding is org-free everywhere except the self-hosted
unity runners — runner groups are org-scoped, and the fleet exists for Make-it-Sing alone
(the one private repo, past hosted ~14 GB disk); every other repo is public, free on
hosted. Docker image declarations spell the org 27 times across two files
(mirror-prefixed `x-base-images` refs + `mirror.prefix` in docker-devkit.yaml) joined
only by startswith, silent in both directions (off-prefix refs quietly unmirrored; a
changed prefix reports "Mirrored images: 0" green). `built_images` had already drifted
twice: capture-tool and Make-it-Sing build images in CI via pre-canonical inline jobs
that never pass `--push`/`REGISTRY` — nothing shelved, nothing tree-tagged, invisible to
release notes — and MiS is pinned to a docker-devkit whose build verb no longer parses
`--mode ci` (`fc5bc25` replaced it). The decision set is Phase 8 below (operator rulings:
the hosted default flips at landing with no validation step; the package and config
renames; derived `built_images`; the stale-spelling lint dropped outright; mirror
injection; the resweep folded into the standing sweep). The prior record's "next session
opens at the placeframe-capture-tool cutover" is SUPERSEDED: Phase 8 is the very next
work; the capture-tool node follows the resweep, cutting over directly into the Phase 8
grammar. Phase 7's per-repo specifics are amended in place where superseded.

Open carries, decisions pending: build-artifact-registry's wrapper-era 3.15 carry is RESOLVED
— the cutover deleted the wrapper (its reusables pin `66df38b`, past the 3.13 pin), confirmed
at the tier close. Still open: its origin remote still spells the ci-devkit SSH URL (redirects cover
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

Carried risks: none open. The unity self-hosted fleet's runner version passed its ≥ 2.336.0
gate live — PR #9's compile legs (the fleet's first `$/` exercise on that pool) ran green.
The hosted half retired earlier: PR #3's green re-run certified the install trio's first full
live pass (`$/` self-reference resolution from a called reusable works on a current hosted
runner).

Session record (2026-10-11, Phase 8.1 executed): all five changes landed on local dev as five
code commits plus AGENTS.md and this record. One plan-mechanic correction, verified against
the live docs before writing: GitHub has NO comma-splitting in `runs-on` — a string is one
label, so the plan's literal `self-hosted,unity` spelling would queue a job forever on a
label no runner holds; the input is therefore a JSON array string (default `["ubuntu-latest"]`)
consumed as `runs-on: ${{ fromJSON(inputs.runs-on) }}` (the docs' sanctioned mix-strings-and-
variables array), and Make-it-Sing's 8.3 spelling is `["self-hosted", "unity"]`. Getters and
every other reusable stay fixed, and the wipe-workspace/safe-directory pre-steps stay (inert
on hosted, load-bearing on reused runners); lint-workflows (actionlint + zizmor) is green over
the shape. The package rename (`release_devkit` → `github_actions_toolkit`, distribution
`github-actions-toolkit`) is consumer-invisible — console-script names unchanged, uv.lock regen
a pure name swap, wheel verified to still ship `py.typed`/`zizmor.yaml`/`third-party` with the
redundant hatch `include` block deleted (this repo's Phase 7 hygiene instance). The
`publish.yml` flip is hard (DEFAULT_CONFIG_PATH, the repo's own config `git mv`'d, plan error
message, tests) — `built_images` now fails at load as an unknown key (tested, extra=forbid).
`built_images` is deleted from PublishConfig; `IMAGE_MANIFEST_PATH = workloads/images.yml`
(named contract with docker-devkit) keys the release verb's expectation, the loud edge re-keyed
to the declaration's presence: manifest present + no digest shards (nor the bare fallback) at
the certified SHA = red via the oras pull failure. The stale-spelling lint is dropped (constant,
check, fixture) — zero `release-devkit` spellings survive in-repo. Battery green at the tip:
preflight-python (161 tests, ruff/format/basedpyright/deptry), lint-workflows,
validate-release-plan; the rename ripple was fixup-autosquashed so every intermediate commit is
ruff-clean (targets verified branch-local first). Sandbox venv note: the rename hit the known
stale-wrapper pitfall — `uv sync` does not regen console scripts when the version is unchanged,
`uv sync --locked --reinstall-package github-actions-toolkit` materialized them; fresh installs
immune.

Session close (2026-10-11, 8.1 pushed): the operator pushed toolkit dev at `48250c4` — that
tip IS the 8.3 resweep pin (nine commits over the prior tip `98acf90`: the two pre-session plan
records, five code, AGENTS.md, the execution record). Next session opens at Phase 8.2
(docker-devkit `0.3` → `0.4`): collapse the manifest candidates to `workloads/images.yml` +
`workloads/images.lock` (fixtures retarget to the real path), mirror-prefix injection from
`docker-devkit.yaml`'s `mirror.prefix` with the double-prefix guard and the empty-`mirror`-section
error, `up`'s `--pull-unmirrored` branch deleted, the `is_mirrored`/startswith matching and the
silent "Mirrored images: 0" success mode die, AGENTS bridge sentences drop; standing laws apply
(one repo one PR through its gate, promote to `main`, stable publish `0.4.0`, prose and code in
separate commits, `--refresh` on relocks). Pull the docker-devkit clone before touching it
(its local dev lags the phase-4/promotion tips); its consumers' `x-base-images` flips ride 8.3,
not 8.2. The plan-record commit for this close rides local until the operator's next push.

Session record (2026-10-11, Phase 8.2 executed on docker-devkit): branch `mirror-prefix-injection`, five commits off dev
`ae0ec2b` (the clone was already current — the prior close's lag warning was stale; local dev = origin dev = main, PR
#11's tip, `docker-devkit-v0.3.0` tagged there). One plan ambiguity resolved by identification, on the record: the
phase's "`up`'s `--pull-unmirrored` flag" names a flag that NEVER existed in docker-devkit's history — it is
`--allow-upstream-fallback` (the flag's own help text reads "Pull unmirrored lock entries from upstream at the same
digest instead of failing closed", which the plan compressed). Scope of the deletion follows from the plan's own
clause that `is_mirrored`/`upstream_ref` die completely — that is only achievable if the upstream-substitution escape
dies with the flag (the substitution IS `upstream_ref`), while the fail-closed probe stays as the loud edge:
`upstream_fallback`/`write_fallback_overlay`/the `run_build` `env_overlay` plumbing are deleted, replaced by
`enforce_mirrored` (probe every lock entry — all mirror-prefixed by construction — hard error with the flag hint
removed from the message; the remedy the text teaches is CI's mirror job, never an org-namespace push). Landed:
manifest resolution collapsed to `workloads/images.yml` + `workloads/images.lock` (`MANIFEST_CANDIDATES`/
`MANIFEST_LOCK_PAIR`/`LOCK_CANDIDATES` and the `compose*.bake.yml` glob in `declared_references` die; fixtures
retargeted, including the version-coupling fixtures collapsing to the single manifest with upstream-native values);
prefix injection (`mirrored_ref(reference, prefix)` is the only join — double-prefix guard raises, `x-base-images`
non-empty with no `mirror:` section raises in `build` via the `update_lock_entries` phase extraction, which also
solves basedpyright's narrowing on the config-or-None); the mirror verb copies EVERY declared reference
(`crane copy {ref} {prefix}/{ref}`, `mirror_targets` dies with the startswith matching); lock values stay
byte-identical (digests resolve against upstream, recorded under the derived name; digest-pinned declarations pass
through prefixed; cached entries still skip on the derived base). Workflows untouched — the toolkit pin stays
`66df38b` (the repin to `48250c4` + `publish.yml` rename ride 8.3's resweep leg, per plan; consumers' `x-base-images`
upstream-native flips are likewise 8.3, and the double-prefix guard makes a pre-flip prefixed declaration a LOUD
error on 0.4 — expected, the atomic-cutover pressure by design). No relock (no dependency changes; the `--refresh`
law had nothing to do). `major_minor` `0.3` → `0.4` in its own commit. AGENTS.md rewritten in the prose commit (bridge
sentences gone, "Mirror namespace" section re-authored for injection, `up`'s flag dropped from its row).
Verification: `scripts/preflight.py` green end to end (ruff/format/basedpyright/deptry/sync-ruff/pytest — 132
tests, down from 150: the legacy-resolution, inversion, fallback, and overlay classes died, the injection/guard/
enforce classes arrived), and lint-workflows + validate-release-plan green against a worktree of the toolkit clone
AT THE PIN `66df38b` (CI parity — the toolkit tip expects `publish.yml`, which this repo carries only from 8.3).
Handoff: operator pushes the branch, opens the PR, labels after CI certifies (MERGE_BOT/evergreen-dev wiring
already live from PR #11), merges, promotes dev → main; the stable channel then publishes `docker-devkit 0.4.0`.
After that, 8.3 opens (the resweep list; placeframe's leg still queued behind PR #136's landing sequence).

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
  workflows). Verified in the bashrun pilot on both channels — dev prerelease and stable
  publish rode the composite onto PyPI; the inline-verb fallback is dead.
- `env` context in a composite step's `if:` (the NuGet login's presence gate): the false half
  (absent `NUGET_USER`, login skipped) live-exercised on every bashrun composite run; the true
  half (the login actually gating on) awaits placeframe's swept leg.

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
  Landed and closed green on both channels (see Execution state).
- **placeframe-capture-tool** after Phases 3–4: CANCELLED by operator ruling — capture-tool is
  a plain Phase 7 sweep repo; its would-be certifications (mirror + preflight, unity build
  per-leg base-version stamping, docker fanout, update-pr-draft-release in the build context)
  ride the sweep's first exercising consumers.

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
runs); one repo = one PR landing via its own merge-gate; every repo completes through `main`
during the sweep — land on `dev`, promote `dev` → `main` (fast-forward, operator-owned), let
the stable channel publish the new line — and each repo relocks onto the latest published
versions of every dependency at its cutover (stable spellings once the upstream has promoted,
dev prereleases before that; floors may keep the `>=X.Y.Z.dev0` spelling; receivers on the
default branch see stable lines as each upstream promotes); update stale agent docs alongside
code (instance:
build-artifact-registry's AGENTS.md names the binding repo by its abandoned intermediate
spelling in the release-flow section).

**Sweep order** (operator rulings 2026-10-11: the infra trio is SKIPPED entirely — its
preflight/merge-gate adoption is dropped from this plan, and its unpushed `.python-version`
pins ride each repo's next natural landing or an operator push; placeframe precedes
placeframe-capture-tool because capture-tool consumes placeframe's UPM packages, so
placeframe's new line must exist on the registry before capture-tool relocks onto it; Nessle,
ObserveThing, StatefulUnity go last). Devkit self-cutovers first (build-artifact-registry,
github-actions-toolkit's own files beyond `$/` refs — none needed, python/docker/unity/devkit
repos themselves), then simple publishers (logger-conf, openapi-client-codegen,
pydantic-settings-pulumi — lbe-toolkit removed from the tier by operator ruling 2026-10-11),
placeframe, placeframe-capture-tool, then Make-it-Sing and lbe-toolkit (lbe-toolkit's
cross-repo edge consumes placeframe's UPM line, so placeframe must publish its new line
before lbe-toolkit relocks onto it; Make-it-Sing rides the same tier by the same ruling;
lbe-toolkit's operator prerequisites verified before its label), then Nessle, ObserveThing,
StatefulUnity. Phase 8 (below) lands as the very next work: its resweep tier covers the
already-swept consumers (placeframe's leg after PR #136's landing), and the remaining
nodes above cut over directly into the Phase 8 grammar.

**Per-repo specifics (from reconnaissance; mechanics re-aimed).** placeframe: 8×
`registries:`→`registry:`+`identity:`, drop `ci_workflow:`, `built_images: true` confirmed
(the key dies at Phase 8 — derived, never re-added),
mirror-images precedes preflight (postgres FROM mirror-pinned base), `.github/workflows/
AGENTS.md` documents the OLD contract — prose update is load-bearing, `cesium.yml`
dispatch-only gets signature checks + wrapper-conformant checkouts; its in-flight
`more-ci-fixes` branch (pin→ed406a0) folds or is superseded; placeframe additionally keeps
`get-docker-matrix`-consuming local docker legs until Phase 4's matrix covers them, and
`publish-compose` local permanently. Make-it-Sing: landing strategy ci-support-redux → new
shape → green → merge-gate → evergreen `dev`; the `built_images` key dies at Phase 8
(derived, never re-added); replace exact docker-devkit pin with a `>=0.4` floor; the
repo-local `build-livekit-token` job is superseded by Phase 8's canonical
`build-docker.yml` call carrying the self-hosted `runs-on` override; its images.yml refs
go upstream-native at the same relock. lbe-toolkit: build on ci-support-redux, 1.0→1.1
all three packages, delete legacy `publish-config.json`, npm identities
`org.outernet.lbetoolkit[.livekit|.photon]`, then retire old ci.yml/release.yml.
placeframe-capture-tool: app `builds` dict→list, add `update-pr-draft-release`, adopt new-line
UPM pins (verify consumed set), supersede stale local branches; its inline `--mode ci`
docker job dies for the canonical `build-docker.yml` call and its refs go upstream-native
(Phase 8).

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

## Phase 8 — binding hardening: hosted-runner default, the two renames, derived
built_images, mirror injection (2026-10-11 operator rulings; executes as the very next
work, before the remaining Phase 7 nodes)

Driver: cross-org readiness (see the session record above) plus the drift surfaces the
same investigation caught. Order inside the phase is load-bearing: 8.1 (toolkit) lands and
is pushed first — its fresh SHA is the resweep pin — then 8.2 (docker-devkit `0.4`), then
8.3. Standing laws all apply (one repo one PR through its gate, promote to `main`, stable
publish; the fresh-SHA law; prose and code in separate commits; `--refresh` on sweep
relocks).

### 8.1 github-actions-toolkit (one node, several commits)

- `runs-on` becomes a string input on the fanout legs of `build-unity.yml` and
  `compile-check-unity.yml`, default `ubuntu-latest` AT LANDING (operator ruling: flip
  now, no validation step — hosted is known-good; public repos run free on hosted and the
  self-hosted fleet exists for Make-it-Sing alone, the one private repo past hosted
  disk). Getters and every other reusable stay fixed. Make-it-Sing spells
  `with: runs-on: self-hosted,unity` at its cutover; every already-swept unity repo flips
  to hosted atomically at its 8.3 repin. Side effects accepted, later sittings: the
  runner-group roster shrinks toward MiS-only and the Hetzner fleet likely downsizes.
- The Python package renames `release_devkit` → `github_actions_toolkit` — package
  directory, all imports, pyproject name and package-data paths, script entry-point
  module targets; console-script NAMES unchanged (public API); uv.lock regen.
  Consumer-invisible: consumers invoke script names only. The external PyPI
  `release-devkit` (StatefulUnity's legacy `uvx` pin) is a different artifact, untouched.
- The consumer config renames `release-devkit.yaml` → `publish.yml` — hard flip at
  `DEFAULT_CONFIG_PATH`, no accept-both. The org config-file law gains its one exception
  sentence: the binding's consumer config is `publish.yml` (the workflow family's `.yml`
  spelling). Every consumer renames in the same commit as its 8.3 repin.
- `built_images` is deleted from `PublishConfig`; release derives the expectation from
  the existence of `workloads/images.yml` at the repo root — a named contract with
  docker-devkit in the leg-schema-keys class (post-8.2 exactly one candidate path). The
  loud edge is preserved and re-keyed to the true declaration: manifest present + no
  digest-manifest shards at a certified SHA = red release. The capture-tool/MiS "gaps"
  dissolve here — they were never flag typos; their jobs never shelved (8.3 fixes that).
- The stale-spelling lint is DROPPED entirely — `STALE_TOOLKIT_SPELLING`, its check, its
  fixtures, the prose (operator ruling: the fleet is operator-owned, the migration bridge
  is over, no replacement allowlist; the redirect's residual risk — org-internal name
  reuse — is accepted). With it gone the rename sweep has zero in-repo survivors.
- AGENTS.md revision rides as prose commits: the "two names survive the rename" ruling is
  superseded by this phase; the `workloads/images.yml` contract and the `publish.yml`
  flip are recorded at their homes.

### 8.2 docker-devkit (`0.3` → `0.4`; the minor carries the grammar break)

- The legacy manifest pair dies: `MANIFEST_CANDIDATES`/`LOCK_CANDIDATES`/
  `MANIFEST_LOCK_PAIR` collapse to `workloads/images.yml` + `workloads/images.lock`; test
  fixtures retarget to the real path (they were the legacy path's only live users); the
  AGENTS bridge sentences drop.
- Mirror prefix injection: `x-base-images` values become upstream-native; the
  mirror-prefixed form is derived from `docker-devkit.yaml`'s `mirror.prefix`. `build`'s
  lock loop drops the strip-prefix-to-inspect-upstream special case and writes
  `{prefix}/{ref}@{digest}` — lock values byte-identical, zero lock churn, no
  re-mirroring. The `mirror` verb's `is_mirrored`/`upstream_ref`/startswith matching
  dies; targets are every declared ref (`crane copy {ref} {prefix}/{ref}`); the silent
  `Mirrored images: 0` success mode dies with it. New loud edges: `x-base-images`
  non-empty with no `mirror:` section = error; an already-prefixed ref = error (the
  double-prefix guard). `up`'s `--pull-unmirrored` flag and branch are deleted —
  unmirrored lock entries become unconstructible.

### 8.3 Fleet resweep + the remaining Phase 7 nodes (folded to the Phase 8 grammar)

- Resweep, already-swept consumers, one PR per repo through its gate, sweep order:
  build-artifact-registry, bashrun, python-devkit, logger-conf,
  openapi-client-codegen, pydantic-settings-pulumi, unity-devkit, docker-devkit (self),
  placeframe — each: repin every `uses:` to the 8.1 SHA + `git mv release-devkit.yaml
  publish.yml`, one commit. placeframe's leg lands only after PR #136's landing sequence
  completes (unchanged) and additionally relocks onto docker-devkit `0.4` and rewrites
  its 16 `x-base-images` refs upstream-native. The repin carries the hosted-runner flip
  to the already-swept unity repos atomically.
- The remaining Phase 7 nodes cut over directly to the Phase 8 grammar — no intermediate
  `release-devkit.yaml` state, no flag. placeframe-capture-tool: the inline
  `uv run build --mode ci` job dies for the canonical `build-docker.yml` call (brings
  `--push`, `REGISTRY`, shelf shards, tree-tags); docker-devkit relock onto `0.4`; its 7
  refs upstream-native; `builds` dict→list and `update-pr-draft-release` as already
  specified. Make-it-Sing: canonical `build-docker.yml` replaces the repo-local
  `build-livekit-token` job; `with: runs-on: self-hosted,unity` on its unity legs;
  docker-devkit `>=0.4` floor replaces the exact poisoned pin; its 3 refs upstream-native;
  verify how stale `livekit-token` on ghcr is at cutover. lbe-toolkit: unchanged except
  the `publish.yml` spelling. Nessle, ObserveThing, StatefulUnity: cut over straight to
  `publish.yml`, hosted runners by default — the destination org needs no runner story,
  the cross-org outcome this phase exists for.

### 8.4 Recorded end states (this session's deferrals, not this pass)

The images.yml + docker-devkit.yaml consolidation — one subject one file; at the merge
the toolkit's built_images derivation goes content-level (declares ≥1 buildable service)
or takes an explicit marker, else lifecycle-only repos false-positive; the mirror prefix
and built-image tag namespaces become owner-derivable the way the shelf derives from
`GITHUB_REPOSITORY`. unityci/editor mirror entries for hosted pull speed — only if the
hosted legs' multi-GB image pulls annoy. The org-move operational checklist (org
vars/secrets, merge-bot App installation, rulesets, trusted-publisher rebinding on the
package registries) — operator sittings, not code. Runner-group roster shrink and
infra-github-runners downsizing — later sittings.

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
| SHA pin law | **the core check**: every `uses:` ref to github-actions-toolkit (workflow or action) is a full 40-hex SHA; all refs to it in one repo carry the same SHA; the stale-spelling detector was dropped by Phase 8 ruling (operator-owned fleet, the migration bridge is over, no replacement allowlist); within-file YAML anchors on the `uses` scalar sanctioned |
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
- images.yml + docker-devkit.yaml consolidation — the recorded end state (Phase 8.4): one
  subject one file; at the merge the toolkit's built_images derivation goes content-level
  (declares ≥1 buildable service) or takes an explicit marker, and the mirror prefix and
  built-image tag namespaces become owner-derivable (the cross-org portability answer).
- unityci/editor mirror entries — only if the hosted unity legs' multi-GB image pulls
  annoy.
- Path-diff change-detection bug (build inputs outside a package's declared `path` are
  invisible) — parked at `todo/CRITICAL-BUG.md`.
- Any change to release.yml's inline delivery model beyond the composite; any org-level
  workflow mechanism; renaming canonical workflow filenames (npm/nuget publisher bindings
  forbid it).
