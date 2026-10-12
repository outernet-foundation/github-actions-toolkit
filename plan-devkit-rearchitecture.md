# Devkit rearchitecture — binding-layer consolidation, package split, fleet cutover

Status: the execution plan for the remaining fleet cutover — the post-placeframe sweep queue
(lbe-toolkit next) plus the unswept Phase 7 nodes. Everything landed is described by
the repos' AGENTS.md files and git
history; this file holds only what future sessions need: the remaining queue, the laws that
govern it, and open carries. It consolidates and supersedes the earlier plan docs
(release-devkit-finish, ci-refresh-seed, zizmor-audit — residue in `todo/supply-chain-control.md`
— plan-reusable-workflow-migration). Decisions are binding for execution sessions. Cadence: one
session per PR where practical, each landing on `dev` — for the toolkit itself by operator push
(ruling: the repo's own merge-gate is not worth it, may be repaired later; consumers keep the
merge-gate) — each session sized to the context-window smart zone (operator ruling): when in
doubt, split; commit discipline per AGENTS-SHARED (prose and code in separate commits, no
trailers).

## Where things stand

Landed and promoted (dev = main everywhere, stable lines live on the registries): the binding
split (github-actions-toolkit holds every reusable workflow, the release composite,
`lint-workflows`, the merge-gate bot, the matrix helper, runner provisioning;
build-artifact-registry is the registry-primitives PyPI dep; the old ci-devkit distribution is
frozen forever, no yank), domain purification (unity-devkit, docker-devkit, python-devkit), the
release composite's channel-input redesign, the workflow_call-only merge-gate reusable, the
draft-release rendering redesign, oras provisioning in the release verb, the digest-shard
merge, the forced-publish clause, Phase 8.1 (hosted `runs-on` default, the
`github_actions_toolkit` package rename, the `publish.yml` config flip, derived `built_images`,
stale-spelling lint dropped), Phase 8.2 (docker-devkit 0.4: manifest candidates collapsed to
`workloads/images.yml`+`images.lock`, mirror-prefix injection, fail-closed unmirrored probe),
and the 8.3 resweep legs one through nine (build-artifact-registry, bashrun, python-devkit,
logger-conf, openapi-client-codegen, pydantic-settings-pulumi, unity-devkit, docker-devkit
self — every `uses:` repinned, configs renamed to `publish.yml`, merged through their gates,
promoted; channels silent by design — no package path touched; placeframe ninth, where the
channels were NOT silent by design — the 2.0 bump forced the publish, see below). Current
stable lines: bashrun 0.8.1, build-artifact-registry 0.2.1, python-devkit 0.3.1,
unity-devkit 0.3.0 (`org.outernet.playerbuild` 0.3.0 on npm `latest`), docker-devkit 0.4.1,
logger-conf 0.3.1, openapi-client-codegen 0.3.2, pydantic-settings-pulumi 0.3.0. The
2026-10-11 ~22:05 UTC wave republished bashrun/build-artifact-registry/logger-conf/
python-devkit/openapi-client-codegen (config-rename + toolkit-repin legs only — package code
unchanged; python-devkit 0.3.1 does NOT carry the ruff 0.17 triage, `9945222` still unlanded).
That wave pinned the toolkit at `48250c4` while placeframe and capture-tool spell `8e2b332` —
two SHAs in the wild, per-repo uniformity intact. The stray `bashrun 0.6.0` orphan stays on PyPI
by ruling (untagged; version math is tag-driven and never references it).

placeframe: the 8.3 leg LANDED through PR #137 (operator ruling: the sweep rode the operator's
`2.0` branch — the all-packages major_minor bump plus the sweep commits — landing before the
promotion, not after it). Contents: every `uses:` repinned to `8e2b332`, `release-devkit.yaml`
renamed `publish.yml` with `built_images` dropped (derived from `workloads/images.yml` presence
at the tip), the 16 `x-base-images` refs flipped upstream-native (the lock regenerated
byte-identical through docker-devkit 0.4's `build --lock-only` — crane-copy digest equality
held), relock onto docker-devkit 0.4.1 with ruff held at 0.14.14, hatch-include hygiene,
agent-doc updates. At the merge the dev channel published the first 2.0-line prereleases of
all nine packages (`2.0.0-dev.1320` npm/nuget, `2.0.0.dev1320` PyPI — the bump forces publish
on untouched paths; nuget's flatcontainer lagged the green run by several minutes — CDN
propagation, not a skip). Outstanding placeframe-side: only the dev → main promotion
(operator) — ships the stable 2.0.0 lines, cuts the CalVer release, resets `dev-builds`; after
it, downstream relocks spell stable pins instead of dev prereleases. `publish-compose` stays
local permanently (repo-side law, recorded in placeframe's workflows AGENTS.md).

placeframe-capture-tool: DONE-BUT-UNLANDED — the cutover is fully executed and locally verified;
only the operator push, the PR through its gate, and the dev→main promotion remain. Branch
`toolkit-cutover` @ `3079211` in the local clone (six commits ahead of `origin/dev` = `ee0c8a2`,
clean tree). Contents: the atomic cutover (all three workflows on the toolkit reusables at
`8e2b332` — unity legs on the hosted default, no `runs-on`; `publish.yml` with list-form builds;
docker-devkit 0.4.1 + the 7 image refs upstream-native + the lock regenerated byte-identical;
tool relocks with ruff held at 0.14.14; new `scripts/preflight.py`; wrapper composite and
actionlint.yaml deleted; no `id-token`/`NUGET_USER` — nothing publishes to package registries),
the 2.0 repins (UPM `2.0.0-dev.1320` + `playerbuild` 0.3.0; PyPI `==2.0.0.dev1320` in zed and
scripts; pylocks regenerated), the `ARFoundationCameraProvider` rename placeframe 2.0 demands,
agent-docs updates, and the manifest slimmed to arfoundation-transitive resolution (core +
apiclient ride arfoundation's closure; logging/auth/playerbuild/zed-client/r3/unitask stay
direct — the app consumes the first three and nothing in the closure provides them). All local
gates green: preflight-python, the full preflight script (codegen gate zero-diff),
lint-workflows, validate-release-plan, two full APK builds. r3 ruling from this leg: 1.3.1 is
forced by the 2.0 packages' own dependency floors (UPM indirect minimums — verified live; not
manifest-downgradeable), and the operator's 1.2.9 harness pin in placeframe sits below placeframe's
own packages' declared 1.3.1 floors, so it cannot hold either; a fleet-wide 1.2.9 requires
placeframe-side package.json changes plus a new dev publish.

Remaining queue: lbe-toolkit next (gate satisfied — placeframe's 2.0 UPM line exists on npm as
`2.0.0-dev.1320` prereleases; re-spell to stable once the promotion lands), Make-it-Sing, then
Nessle, ObserveThing, StatefulUnity last (straight to the Phase 8 grammar — `publish.yml`
spelling, hosted runners by default; the destination org needs no runner story). Local clones
lag where sessions left them — the operator pulls before each is touched.

## Open carries and blockers

- **ruff 0.17 wave** (will recur at every remaining relock): python-devkit's canonical triage
  (`9945222`, local branch `ignore-more-ruff-rules`, UNLANDED) adds ASYNC119 + PLW0717 to the
  "Temporarily ignored (will be enable when conventions are established)" block with rationale.
  Until that line publishes, no consumer can both take ruff 0.17 and stay green (sync-ruff
  --check compares the committed `ruff.base.toml` against the LOCKED python-devkit's canonical).
  The wave per repo, at its next relock: canonical re-sync + relock onto 0.17 + the ~40
  mechanical fixes (RUF105 converts `# noqa:` to `# ruff: ignore` — UNREADABLE by ruff 0.14, so
  the conversions MUST land in the same commit as the 0.17 lock bump, never before; RUF069
  float-equality in tests; RUF201 selector syntax; ICN001 `datetime as dt` excluded for
  generated datamodels). ruff 0.17's stricter noqa parser also warns (warning only, not a
  finding) on the org-mandated `# noqa-wrapper:` header. placeframe's lock holds ruff at
  0.14.14 for exactly this reason.
- **Toolkit lint's one live network dependency**: `ensure_actionlint()` fetches the upstream
  checksums file on every run even when the binary is warm-cached (offline-persona hole;
  zizmor's hashes are already constants here), and the bootstrap's `curl -fsSL` calls carry no
  timeouts — a stalled connection hangs forever, silently. Fix candidates: checksums as repo
  constants (the zizmor pattern) + `--connect-timeout`/`--max-time` on the two downloads.
- build-artifact-registry's origin remote still spells the ci-devkit SSH URL (redirects cover
  it; rename housekeeping is host-side).
- **Fleet interpreter pins**: `.python-version` (`3.13`) committed but unpushed on the
  remaining repos' checked-out branches (lbe-toolkit / Make-it-Sing / Nessle / ObserveThing on
  `ci-support-redux` each; StatefulUnity on main) — each rides its repo's cutover.
  `requires-python` ranges stay open by design (operator declined bounding; the pin wins
  discovery — the original CPython 3.15 drift shipped no cp315 wheels for the locks' pins, and
  only pinned repos were immune).
- **Infra state future legs rely on**: evergreen-dev rulesets carry ref mechanics ONLY —
  required checks are removed by ruling (check policy lives in the gate verb's all-green
  battery; a ruleset-level check couples the program to check names that drift on every
  cutover). The main envelope is exactly: only the operator updates, updates are fast-forwards,
  deletion blocked for everyone (`required_linear_history` removed — dev tips are the gate's
  `--no-ff` merge commits by design; "main only ever advances to a promoted dev SHA" stays
  procedural). The GitHub App token cannot push or merge — lands go through each repo's
  merge-gate or the operator — but it DOES read run lists, views, and logs on the public repos
  (`GH_TOKEN=$(uv run --project /pulsar/scripts mint-github-app-token) gh ...`; never
  `gh run watch` — it burns the rate limit).

**Accepted risks, on the record:** the unity reflection-driven environment-materialization
failure mode (compiles green, silently misapplies settings, surfaces as mysterious consumer
builds) has NO detector in the fleet — the operator chose compile-gate uniformity over the
smoke test; abandoned PRs' draft releases linger (hidden, the accepted leak); the org-internal
name-reuse risk of the toolkit's redirect is accepted.

**Standing toolkit-design rulings:** preflight's sequential lint→plan→script steps are
fail-fast economics (the accepted premium over a parallel max() is one lint wall-clock per
green PR); lint-in-integrate is certification for trusted authors, never a security boundary —
PR-authored YAML can simply delete it (the PPE class of threats is answered by the org-level
rulesets below, not by lint placement).

**Verification practices:** confirm load-bearing registry facts on the version-scoped endpoint
(the unversioned `/pypi/<pkg>/json` serves stale CDN cache); use `uv lock --refresh
--upgrade-package <pkg>` on sweep relocks (both the plain lock and plain `--upgrade-package`
silently keep stale pins off a warm index cache); the sandbox's default `uv` (0.11.14 at
`/usr/local/bin`) shadows the host-shared 0.12.15 at `~/.local/bin` — prefix
`PATH="$HOME/.local/bin:$PATH"` (shell exports do not persist between tool calls); after
editing a workspace member's entry points, `uv sync` does NOT regenerate stale console-script
wrappers when the member's version is unchanged — `uv sync --reinstall-package <pkg>`
(fresh CI installs immune); `uvx --from <local-path>` serves a stale cached env through
`--refresh-package` — only outer `--no-cache` forces the rebuild; nuget.org's flatcontainer
index and blob endpoints lag a green dev publish by several minutes — a 404 there right after
a green release run is CDN propagation, not a missing publish (verified live at the placeframe
2.0 merge: npm and PyPI listed within seconds, nuget took ~6 minutes).

## The model: two layers, one seam

The `-devkit` suffix names two different kinds of repos, and every smell the rearchitecture
found was a piece sitting on the wrong side of the seam. The test is one question: **does this
code know GitHub exists?**

- **Domain toolchains** — unity-devkit, docker-devkit, python-devkit (+ logger-conf,
  openapi-client-codegen, pydantic-settings-pulumi, lbe-toolkit as simple publishers): pure
  "how to build/test/mirror/publish-in-the-abstract X", meaningful from plain bash on a laptop,
  coupled by domain, PyPI-pinned via each consumer's `uv.lock`. Hard law: no ambient `GITHUB_*`
  reads, no `::` annotations, no `$GITHUB_OUTPUT` writes in domain code. Convention: verbs
  print neutral output (JSON leg lists, plain banners); decoration may detect the platform,
  logic never may.
- **The platform binding** — github-actions-toolkit: everything that knows GitHub Actions
  exists. One repo, clone-pinned, dependency-of-nothing. Holds: all reusable workflows, the
  release composite, `lint-workflows`, the merge-gate bot, the release/delivery verbs (OIDC
  trusted publishing, Releases API, `GITHUB_REF` parsing are platform-bound), runner
  provisioning (vendored `third-party/`), and the matrix helper.
- **build-artifact-registry** — registry primitives for pushing/pulling build artifacts,
  locally or remotely (`builds`, `cache`, `setup_oras`, `registry_auth`). Purely registry
  concerns; no presentation, no runner knowledge. ghcr is a registry choice passed as a
  parameter, not platform coupling.

Supporting laws:

- **Verbs are named for side effects, never execution context.** "ci" is a context; shelf/push
  is a side effect. Shelving is implied by supplied registry env; docker keeps its explicit
  `--push`.
- **Stable-CLI-API doctrine is fleet law**: script names and flags are public API for every
  devkit — structure (in github-actions-toolkit) and code (in consumer locks) are pinned by
  different mechanisms, so the YAML's expected verb surface must not move silently.
- **Prose rule**: fleet docs retire bare "registry" — "package registry" for the publishing
  side (PyPI/npm/NuGet), "build-artifact registry" for the OCI artifact side.
- **Fleet YAML formatting is retained, not reformed**: blank lines between jobs and top-level
  keys, permissions and secrets as block maps. Cutover changes structure, not style.
- **No GitHub merge queues, permanently**: they land merge-group trees, never the certified
  PR head. actionlint stays; reassess only if upstream stalls on `$/`.

## Verified platform mechanics (do not re-derive)

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
  (allowTipSHA1InWant) — verified live against a merge-ref SHA. `actions/checkout` cannot make
  this clone: it refuses any `path` outside `$GITHUB_WORKSPACE` (actions/checkout#197, every
  release since v2), and the toolkit clone must live outside the workspace
  (consumer-checkout's `git clean -ffdx` would wipe a nested copy; the consumer's zizmor scans
  the repo root, respecting .gitignore but not untracked clones). github-actions-toolkit's
  install mechanism is the hand-fetch inside its `toolkit-checkout` composite — same shape as
  its self-test clone, no token (public org).
- **`uses:` is resolved statically by GitHub, server-side.** No expressions, no env, no
  filesystem. Cross-repo refs must be `owner/repo/.github/workflows/file.yml@ref`; `./` refs
  resolve same-repo at the caller's commit — github-actions-toolkit's own `integrate.yml` calls
  its own reusables via `$/` with no SHA and no self-pin bump. Consequence: a consumer's SHA is
  spelled only in the consumer's own files.
- **Same-org self-hosted runners work in called workflows** (callee uses the caller's runner
  pool); the org `unity` runners qualify — that pool exists for Make-it-Sing alone (the one
  private repo, past hosted ~14 GB disk). `github` context in the callee is the caller's event.
  Caller's `vars` are visible; secrets must be passed per call and forwarded explicitly at
  every nesting hop. `GITHUB_TOKEN` permissions propagate maintain-or-reduce.
- **Outputs chain** through `on.workflow_call.outputs` at each level.
- **Footguns.** `fromJson` on an empty string fails at render time. Nested-call limit is 10
  (this plan uses at most 2). Matrix-derived values interpolated into `run:` lines ride step
  `env` with the run line referencing the variable (zizmor template-injection remediation) —
  the standing law inside every devkit-owned file.
- **The `secrets` context never enters composite-land.** Withheld from action files entirely —
  a parse failure (`Unrecognized named-value: 'secrets'`), not an empty string
  (github/docs#12705) — and unavailable in `if:` conditions even in workflows. Crossing points:
  workflow/step `env:` and step `with:`, in workflow context only. Consequence: the consumer's
  release.yml maps `NUGET_USER` in workflow-level env; the composite gates the login on
  `env.NUGET_USER != ''`.
- **Local `uses:` inside a composite resolves against the consumer's workspace**, not the
  action's own checkout (actions/runner#1348) — composite→sibling references are impossible;
  the native fix is the `$/` self-repository reference (in use for the install trio). The
  release composite stays self-contained regardless — the duplicated prelude is the accepted
  price.
- **Booleans never cross into expression evaluation inside a composite** — inputs arrive
  stringified inside `${{ }}`, where a bare truthiness test reads `"false"` as true and an
  `== true` comparison number-casts `"true"` away from boolean true (each failure verified
  live on the opposite channel). Strings cross safely: forwarded as values or compared as
  strings. This is the channel-input law behind the composite's required string `channel`
  input.
- **GitHub has NO comma-splitting in `runs-on`** — a string is one label. A multi-label input
  is a JSON array string consumed as `runs-on: ${{ fromJSON(inputs.runs-on) }}`;
  Make-it-Sing spells `["self-hosted", "unity"]`.

## The remaining sweep

**Sequencing laws.** One repo = one PR landing via its own merge-gate; every repo completes
through `main` — land on `dev`, promote `dev` → `main` (fast-forward, operator-owned), let the
stable channel publish the new line. Each repo relocks onto the latest published versions of
every dependency at its cutover (stable spellings once the upstream has promoted, dev
prereleases before that; floors may keep the `>=X.Y.Z.dev0` spelling — a `.dev` prerelease
cannot resolve under a short base, and a run-id-keyed floor would die on the first
count-keyed republish). Pin the toolkit tip at cutover, every `uses:` ref one SHA (currently
`8e2b332`, code-identical to `48250c4` — the delta is plan records); the pinned SHA must exist
on the remote before consumer CI runs. Prereleases/new lines must exist on the registry before
downstream relocks reference them. Update stale agent docs alongside code. `--refresh` on
relocks. The docker-devkit-0.4 double-prefix guard makes a pre-flip mirror-prefixed
`x-base-images` ref a LOUD error — the atomic-cutover pressure is by design; upstream-native
flips and the 0.4 relock land in the same commit as the cutover.

**Reference regimes for the five (operator ruling 2026-10-11).** Minimal-invasive: inter-repo
dependency references among the five cutover repos (lbe-toolkit, Make-it-Sing, Nessle,
ObserveThing, StatefulUnity) stay verbatim at their origin/dev spellings, except the enumerated
necessary adjustments — Nessle's and StatefulUnity's project manifests flip
`com.fofx.observething` to a git SHA pin at ObserveThing's tip (`957c7b6`, path
`Assets/Package/Core`), because their tips call APIs absent from every published observething
line (the generic observer interfaces; `ObservableShallowCopy`/`ObservableForEach`). Published
`package.json` edges among the five never flip to git (UPM does not resolve git URLs as
indirect deps) — they ship their existing registry spellings verbatim, accepting temporarily
incoherent floors for registry consumers until the trio republishes. Any other forced change
to an inter-five reference aborts that repo's cutover with evidence. No other repo needs
adjustment: Make-it-Sing's trio refs already resolve to compiling content (nessle git-SHA
`68e19b1`; observething/stateful moving git URLs landing on main tips `f786746` ⊇ `957c7b6`
and `c08203a`), and lbe's registry trio pins compile (its code uses no tip-only APIs).
Application code changes ONLY where an external package at registry-latest demands it:
playerbuild `0.3.0`'s flat `Outernet` namespace (Make-it-Sing's two `66697f3` editor files —
verified at tag `playerbuild-v0.3.0`), placeframe 2.0's `ARFoundationCameraProvider` rename,
livekit-sdk 2.0's `TaskYieldInstruction` await shape. Every reference from the five to a repo
outside the five is a package-registry pin at that package's actual latest published version,
verified per name on npm: placeframe UPM at `2.0.0-dev.1324` until the dev→main promotion
(re-spell to `2.0.0` rides the landing; apiclient may lag on the 1.0.6-dev line — pin actual
latest), playerbuild `0.3.0`, livekit-sdk `2.0.0`. The toolkit `uses:` SHA and the uv.lock
toolchain pins are not dependency references; their own laws stand. Cutover order is fully
independent.

**Per-repo specifics (from reconnaissance; mechanics per the toolkit's AGENTS.md).**

- **Make-it-Sing**: the canonical `build-docker.yml` call replaces the repo-local
  `build-livekit-token` job; `with: runs-on: '["self-hosted", "unity"]'` on its unity legs;
  a docker-devkit `>=0.4` floor replaces the exact poisoned pin; its 3 image refs
  upstream-native; verify how stale `livekit-token` on ghcr is at cutover; landing strategy
  ci-support-redux → new shape → green → merge-gate → evergreen dev. Never label before
  integrate runs (below).
- **lbe-toolkit**: build on ci-support-redux; 1.0 → 1.1 all three packages; npm identities
  `org.outernet.lbetoolkit[.livekit|.photon]` (`.livekit`/`.photon` sit at `0.0.0-local` —
  first new-paradigm publish rides the 1.1 line); delete legacy `publish-config.json`; then
  retire the old ci.yml/release.yml; gated on placeframe's new UPM line; operator
  prerequisites verified before its label (below).
- **Nessle, ObserveThing, StatefulUnity**: cut over straight to `publish.yml`, hosted runners
  by default. StatefulUnity lives in the politically-separate destination org (the cross-org
  outcome Phase 8 exists for; runner groups are org-scoped, which is why the binding went
  org-free).

**pyproject hygiene, remaining repos, every in-tree pyproject.** Delete deptry
`known_first_party` self-declarations (`per_rule_ignores` tables stay); delete `[tool.uv]
prerelease = "if-necessary-or-explicit"` (uv 0.12 deprecates; drop the table when it's the
only key); delete redundant hatch wheel `include` blocks naming files under `packages`.

**Standing constraints.** The GitHub App token cannot push or merge — lands go through each
repo's merge-gate or the operator. The agent never runs `git fetch` and never uses prepo in
these repos: branch plainly in the main checkout (`git checkout -b <name>`), treating the
local checkout as the session's state — origin-side truth arrives through the operator.
**Never label a PR in a repo without a live verification job** (vacuously-true all-green).

**Operator-owned prerequisites.** evergreen-dev ruleset membership for Make-it-Sing +
lbe-toolkit; `MERGE_BOT_APP_ID` var + `MERGE_BOT_APP_PRIVATE_KEY` secret per repo; `UNITY_*`
secrets; npm trusted-publisher rows for the three `org.outernet.lbetoolkit*` names bound to
`release.yml`; a per-repo `NUGET_USER` secret for every nuget-publishing consumer — never
org-level (org secrets are fleet-visible and would switch the login on everywhere). The agent
verifies wiring exists before labeling; it does not prepare the ruleset PR.

**Operator-owned org-level hygiene (threat-model load-bearing, independent of any parked
initiative).** Org-wide push ruleset path-restricting `.github/**` on all branches, bypass =
operator (closes the compromised-member workflow-edit path); fork-approval tier "all external
contributors" on every public repo (fork workflow spellings never auto-run; also rations
hosted-runner slop); org default workflow permissions read-only; "Allow GitHub Actions to
create and approve pull requests" OFF.

## Phase 8.4 recorded end states (deferrals, not this pass)

The images.yml + docker-devkit.yaml consolidation — one subject one file; at the merge the
toolkit's built_images derivation goes content-level (declares ≥1 buildable service) or takes
an explicit marker, else lifecycle-only repos false-positive; the mirror prefix and built-image
tag namespaces become owner-derivable the way the shelf derives from `GITHUB_REPOSITORY`.
unityci/editor mirror entries for hosted pull speed — only if the hosted legs' multi-GB image
pulls annoy. The org-move operational checklist (org vars/secrets, merge-bot App installation,
rulesets, trusted-publisher rebinding on the package registries) — operator sittings, not
code. Runner-group roster shrink and infra-github-runners downsizing — later sittings.

## Consumer end-state

Simple publisher (e.g. bashrun) — `integrate.yml` is `preflight` (uses; the script is a
two-line Python file calling `uv run --locked preflight-python` through bashrun) +
`update-pr-draft-release` (uses, `needs: [preflight]`); `merge-gate.yml` is triggers +
concurrency + one gated `uses:` call; `release.yml` is triggers + concurrency + delivery jobs
of one composite `uses:` each — plus, for nuget-publishing consumers only, one workflow-level
env line mapping `NUGET_USER: ${{ secrets.NUGET_USER }}` (the composite's login gate keys on
its presence; see the secrets-context bullet in verified platform mechanics).

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
scripts), unity `compile-check-unity.yml` call, `update-pr-draft-release` needing
`publish-compose` + the unity fanout; its `scripts/preflight.py` carries the DB battery, and
the calling job's `packages: read` supplies the mirrored postgres the battery pulls. What
stays local is an ownership boundary, not a mechanics one: repo-owned scripts (the preflight
script itself included), `publish-compose`.

## Out of scope (recorded, not planned)

- The `$/` flip's consumer half remains parked: consumers' local-job wrappers
  (checkout/setup-uv) flipping to `$/` — the toolkit flipped its own files already, and the
  actionlint bridge retires by pin bump once a release accepts the spelling.
- Supply-chain initiative — parked at `todo/supply-chain-control.md`. Not adopted there:
  fleet-wide `--min-severity medium`.
- Hotfix release model — parked at `todo/hotfix-release-model.md`.
- Fork-contribution model — parked at `todo/fork-contribution-model.md`.
- Unity license and runner redesign — parked at `todo/unity-license-architecture.md`.
- images.yml + docker-devkit.yaml consolidation — the recorded end state (Phase 8.4).
- unityci/editor mirror entries — only if the hosted unity legs' multi-GB image pulls annoy.
- Path-diff change-detection bug (build inputs outside a package's declared `path` are
  invisible) — parked at `todo/CRITICAL-BUG.md`.
- Any change to release.yml's inline delivery model beyond the composite; any org-level
  workflow mechanism; renaming canonical workflow filenames (npm/nuget publisher bindings
  forbid it).

## Ruled out (do not re-propose without new information)

- An added composite-lint layer (bettermarks/composite-action-lint surveyed).
- The two-composites release split and env+bash-branch channel selection (operator-rejected
  as ugly; the single string-input composite is the settled shape).
