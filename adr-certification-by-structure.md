# ADR: certification by structure — generated lane files, the review anchor, and the conditional trusted trigger

Status: accepted — the design is locked and every open question is resolved. The
2026-11-22 sessions' rulings are recorded below; worked samples live in
`design/stage-splicing/`; execution is ordered and deferred to the next session, which
reads `design/stage-splicing/execution-plan.md` and implements it. Amends `adr-fork-contribution-lane.md`
(D4 and D5 gain the review anchor; the hand-authored consumer-file model and the
lint-enforcement posture are superseded by generation) and `adr-ci-label-modes.md` (the
label no longer claims to be the approval; the review is). The two-tier lane itself, the
label ontology, the strip, the merge machinery, and the D6 signing tiers stand unchanged.
Date: 2026-11-22.

## Context

The review of commit `73df83d` surfaced two defects with one root. The workflow lint had grown
from 378 to 779 lines, and the zizmor config had gained `dangerous-triggers` ignores — both
policing the same thing: the lane's safety invariants lived in hand-authored consumer YAML
(mode gates, terminal gates, queue placement, pair rules, wake contracts), and the only
available police was lint. A second finding compounded it: `build-unity.yml` and
`build-docker.yml` live in this repo, making the two domains first-class citizens of the
certification chain — a layering violation by this repo's own doctrine (the Python already
lives in the domain devkits), which had already produced a live defect: the toolkit's
`build-unity.yml` at one pin threading `--application-id-suffix` into a unity-devkit verb at
another pin that had dropped the flag. Two version surfaces for one domain, skewing.

The operator ruled the governing principle: **lints are a last resort.** Anything a lint
enforces should, wherever possible, be made structurally inexpressible to violate.

The design space is a trilemma. A certification system on GitHub Actions can have at most two
of: platform-enforced safety (the merge decision consumes only what GitHub guarantees — needs
edges, protected refs, credentials), open composition (third parties add certification stages
without a toolkit release), and no compiler (consumers hand-write workflow files). The shipped
branch chose open composition plus no compiler and paid the third column in spelled invariants
plus lint. A closed-spine orchestrator with a certificate protocol (drafted and retracted
within the session) chose platform safety plus open composition and paid in witnesses,
protected ref namespaces, and polling. The chosen leg: **give up hand-authorship.**

Three platform realities framed the trigger ruling. First, a label race exists: a push landing
in an approver's blind spot between viewing the diff and clicking the label certifies the
pushed head, because GitHub labels carry no commit identity and apply to whatever head is
current at click time. The strip covers label-then-push, the lease covers in-run drift, but
push-then-label is uncovered — and the only native act that records a specific commit is a
review (`commit_id`). Second, GitHub ships a default Actions event policy blocking
`pull_request_target` in public repositories: evaluate mode now, enforcement 2026-12-02
(brownouts already ran November 9 and 16), escaped by an org event policy that explicitly
allows the event, targetable by workflow file. Third, the ecosystem survey (Prow, bors, Zuul,
Gerrit, merge queues, dispatch patterns) found no approach that executes external contributors'
build code with real secrets pre-merge and is provably safe; every provable system refuses the
combination (secrets post-merge, or confined to trusted CI config). The human-gated trusted
context is the only family that meets the evergreen requirement.

## Decision: the lane files are generated

Consumer lane files (`integrate.yml`, `preflight.yml`, `release.yml`, `retry.yml`,
`cleanup-pr-releases.yml`) become build artifacts, emitted by a toolkit verb
(`generate-github-workflows`) from a declarative `jobs:` map in the consumer's
`publish.yml`, dict-keyed by job name. The entry is a leaf carrying exactly one source —
`package` (a domain wheel, with an explicit required `repository`), `path` (a
consumer-local stage file), or `uses` (a foreign reusable) — plus `runners` (labels,
overriding the domain's declared default) and `secrets` (slot → repo secret name,
explicit, no conventions). No `with:` block, no `pin` field, no `gates`: advisory jobs
are cut — every spliced job is mode-gated and merge-blocking, uniformly, and tier one
remains the feedback-only surface — and runtime inputs resolve at generation (channel
stamped per target file, everything else from the domain's declared defaults). Topology
is fixed by the generator — gate, preflight, a fan of jobs, `release-pr-builds`,
terminal — never expressible in config: fan, not chain, because a declared job set has
no meaningful order and wall-clock is max-of-durations. Schema discipline is a standing
obligation: the moment the config grows conditionals or per-job needs edges, the
spelling hazards have returned through the back door.

The generator is domain-blind, and the bar is law: **it may know GitHub Actions and its
own spine; every other fact it consumes is either visible in a config file the consumer
owns or a named contract that fails loudly when violated.** No domain names, no secret
vocabularies, no naming transformations — a canonical-maps design and an upper-snake
fallback convention were both drafted and rejected as vocabulary knowledge in disguise.
Secret bindings validate bidirectionally: a slot referenced by the spliced document
without a binding fails generation, and a binding naming a slot the document does not
declare fails generation — typos red in either file.

Pins resolve from single sources of truth. The toolkit's own SHA is the clone the verb
runs from. Domain stage YAML is fetched at the commit stamped into the wheel during the
existing ephemeral-patch publish window (`_toolkit_build_commit`, read from the synced
consumer venv's dist-info RECORD as a file — no domain code executes in the generator):
the wheel names the commit it was minted from, so the YAML fetched at the stamped SHA
is by construction the YAML that lived beside the Python being installed. The
correspondence is machinery-minted rather than physical — the stamp's only writers are
the release pipeline and trusted publishing, so a lying stamp requires compromising
publishing, at which point the game was lost anyway. Git-pinning the domains in
consumer locks was rejected (operator ruling: not the consumption model for Python
packages) despite verifying live that it resolves. Drift is policed by
`generate-github-workflows --check` in the preflight harness — one equality comparison,
the exact geometry `sync-contributor-docs` established (canonical content in the
toolkit, verbatim copies in the consumer, `--check` reds on drift). Hand edits to
generated files are detectable, deliberate, and fail the merge.

Splicing is inlining, not `uses:`: the generator fetches the domain's stage file at the
stamped SHA, parses it, applies mechanical transforms only (toolkit refs rewritten to
the generator's SHA, inputs resolved to literals, job keys and needs prefixed, mode
gates and spine edges stamped, secret slots bound), and emits the jobs flat into the
consumer's file — which is what keeps getter and fanout legs in one file so the matrix
handoff keeps working. No orchestrator reusable, no spine wall, no side channels.
Extension stays open: a new job anywhere in the world is a config line, no toolkit
release. Worked samples — the domain stage file, the wheel stamp, the generator, the
consumer config, the generated output — live in `design/stage-splicing/`.

## Decision: the domains go home

`build-unity.yml` and `compile-check-unity.yml` move to unity-devkit; `build-docker.yml`
(and its compose publishing) moves to boatyard — verbatim moves: the files stay ordinary
hand-authored workflow YAML, browsable and reviewable, carrying their getters and fanout
legs together (the matrix handoff requires one file, which splicing preserves). The
toolkit shrinks to: the merge/delivery spine (gate, merge-if-ready, retry, cleanup,
release verbs), the generator, the checkout composites, and the lint runners. Its Unity
*YAML* goes; unity-shaped knowledge stays by contract — `matrix`'s project→app resolution
and version math, the release-side shelf pulls keyed on `apps.builds`, and the leg-schema
and shelf-grammar named contracts remain binding-owned.

The former OQ2 seam is resolved by the rewrite rule: moved files reference toolkit
surface at their own domain-maintained pins (full spellings replacing `$/`), and the
generator rewrites every toolkit `uses:` ref to the generator's own SHA at splice — the
consumer's view carries one toolkit pin, held everywhere, and a domain's lagging pin can
never skew anything for anyone else. The getter's `| matrix` pipe runs from the toolkit
clone at that same rewritten pin.

And the division the moved files obey is law: **a workflow file contains structural
facts GitHub needs before any process runs (needs, matrix, container, if) and env
bindings — nothing computational.** The Android keystore channel selection (CI vs
production quartet) moved out of workflow YAML into channel-keyed secret bindings in the
consumer's config, and the base64 keystore decode moved into the `build-unity` verb, which
receives the channel-selected quartet as opaque env data plus the channel it already holds;
every line of bash in YAML lives outside the type system, outside the verb's tests, and
inside the zone only zizmor polices. Exactly one quartet reaches any context (see the
reconciliation below).

## Decision: structure over lint, and the lint residue

The contract layer of `lint-workflows` (trigger-keyed wake contracts, mode-gate checks, queue
placement, pair rules, no-secrets scans, the SHA law) is deleted — every one of them policed
hand-authored spelling that no longer exists. What survives: the actionlint and zizmor runners
as second opinions over generated output, and as the primary police of hand-authored stage
bodies and third-party actions (template-injection, unpinned-uses). The zizmor config returns
to `rules: {}` and carries a `DO NOT CHANGE THIS FILE WITHOUT EXPLICIT OPERATOR APPROVAL`
guard. The trigger acknowledgment moves inline: the emitter stamps
`# zizmor: ignore[dangerous-triggers]` at the trigger block of each lane file — verified
against the pinned 1.30.1 binary; precision is the finding's span (the `on:` block), which is
the right scope for files whose only dangerous trigger is the sanctioned one.

## Decision: the review anchor (amending D4 and D5)

The gate verb refuses any mode other than idle unless an approving review exists whose
`commit_id` equals the payload head. The division of semantics: **the review is the approval**
— one uniform meaning, "a write actor examined and vouches for this exact commit," correct in
every scenario including certify-only. **The label is the command** — the wake (the only
write-act wake `pull_request_target` offers) and the mode selection. The `approved-for-*`
vocabulary is retained unchanged: the label names what the approval (recorded as the review)
is for. The approve button's folkloric merge implication is the misnamed element; it cannot be
renamed, so the canonical contributor docs carry the translation (a green check means vetted,
not merged).

The label race closes by construction: a label clicked from a stale tab lands on the current
head, the gate finds no review at that head (only write actors can write one), and the run
refuses loudly with the repair instruction. The strip survives as command-label hygiene: a
push cancels a pending command. Per-head freshness stops being prose about label presence and
becomes a SHA comparison the platform guarantees the data for. Cost: two deliberate clicks per
approval (review, then label), including member self-service — accepted.

## Decision: the trigger ruling and the chain-completion rule

Recorded as standing doctrine: **a trusted-context trigger is acceptable if and only if every
path from stranger action to secret-bearing execution crosses a platform-enforced human act,
and the trusted file's handling of attacker-controlled data is structural rather than
spelled.**

`workflow_run` fails the first prong categorically — its event vocabulary (requested, in
progress, completed) contains no human-gated event, the stranger alone completes the chain
(their fork's own run completing fires the trusted context), and it is PR-unassociated, so
any real use drags in check-posting bots or checks-tab photographs. Its ban stands on the same
logic that accepts `pull_request_target`. The two-stage escape hatch (untrusted
`pull_request_review` completing fires trusted `workflow_run`) exists and stays banned.

`pull_request_target` is accepted, conditionally. The conditions: the wake set excludes
`opened` and `workflow_dispatch`; the trusted files are base-authored and generated; the
review anchor holds; label authority is the gateway; the lease and tree verification stand.
Operational conditions: an org event policy allowing the event, scoped by workflow file to
exactly the two generated lane files, written before any repo adopts tier two (enforcement
2026-12-02; the OQ7 decision); the gate's fork-head checkout resolves against `actions/checkout` v7's
`allow-unsafe-pr-checkout` (the OQ5 decision); cache-save posture moves to push-triggered
workflows (the OQ6 doctrine). Post-acceptance, this repo runs a sanctioned-exception pattern
the vendor documents and warns about — the acceptance is deliberate, auditable, and recorded
in org policy, which is exactly the form the operator demands for flagged mechanisms.

The residuals that survive the ruling, named: D6's accepted risk (post-anchor, contributor
code executes with the Unity license and CI keystore after a two-act human approval);
cache-poisoning class (mitigated by tree-keyed shelf promotion and the read-only cache
tokens); and the trust root itself (nothing validates `dev` against a higher authority — the
operator is the root, encoded in the ruleset).

## Decision: the branch stays in place, cleaned by the landing-time rebase

Rework proceeds in place on `fork-contribution-lane`: the branch keeps taking commits through
the OQ9 integration, and one rebase pass per the workspace rebase style guide lands it — the
pass's excision rule (a change a later change replaces or deletes does not appear in the
rebased history) keeps the dead work (the lint contract layer, the suffix-flag threading, the
superseded hand-authored doc shapes) out of `dev` permanently without a restart. What makes
in-place rework safe: the provisional pin chain is already broken at the root — `49f1cc6`,
the tip that unity-devkit's `4092bdf` and capture-tool's twelve `uses:` refs pin, is orphaned
in the local object store, reachable from no branch local or remote, so nothing live depends
on the pushed branch. unity-devkit's `channel-identity` survives in substance (the in-verb
identity derivation is this design's shape) and takes one re-pin commit targeting the first
merged SHA of the reworked branch; capture-tool relocks its `uv.lock` and re-points its pins
after unity-devkit lands. Landing order (amended by the reconciliation below): the toolkit
branch merges first as T1 (the pinned SHA must exist on the remote before consumer CI
runs), then the org event policy goes up, then unity-devkit, then boatyard, then
capture-tool as the canary (tier-two adoption waits on the org event policy, the OQ7
decision), then the toolkit's self-regeneration lands as T2 — two toolkit landings, not
one.

## Decision: the composites absorb the run's own context (OQ3)

The `head-checkout` input on the preflight reusable and the `save-cache` input on the setup-uv
composite die — the helpers derive both facts from `github.event_name`, which every run carries.
The checkout composite's default becomes event-keyed: an explicit `ref` input always wins (the
gate job's frozen payload head is untouched), a `pull_request` event checks out
`github.event.pull_request.head.sha`, and everything else falls to the candidate spelling — an
unsanctioned event yields the numberless `refs/heads/candidate/`, which fails loudly inside git
under the standing no-emptiness-guard doctrine, no new guard added. The setup-uv composite
restores always and saves only on push-class events: GitHub hands every PR-triggered run a
read-only cache token (the 2026-06-26 platform fact), so the old `!head-checkout` spelling was
instructing a save the official preflight run could only attempt as a warning. The deaths take
the pair rule and the identical-`with:` law with them (nothing is left to keep identical), the
boolean threading expressions in the reusable, and the `with:` block on generated preflight
calls — the generator stamps less. The ref choice was already implicit (the composite spelled
the candidate default before), so the deletion removes a toggle over hidden behavior rather
than hiding explicit behavior. The save-worthy vocabulary is the cache-save doctrine (OQ6):
the sentence "pull-request runs restore, push runs save", classified by event shape, never
by list — OQ3 fixed the mechanism, OQ6 the policy.

## Decision: the review anchor under a sole maintainer (OQ4)

Standing assumption, recorded with its expiry: every consuming repo has exactly one maintainer
for now — true at adoption, not true forever. A second maintainer reopens exactly two rulings
(aggregating reviews across maintainers, and whether one maintainer's CHANGES_REQUESTED vetoes
another's approval); the rest survive at any count. Under the assumption the verdict rule is
the maintainer's latest review at the payload head: Approve passes, and CHANGES_REQUESTED,
COMMENTED, or absence refuses (latest-wins covers self-reversal). Only reviews from write
actors count, in either direction — strangers can submit reviews on public repos, and a
stranger's APPROVED or CHANGES_REQUESTED means nothing here.

Own-PR exemption: a PR whose author holds write-or-above permission on the repo rides the
label alone, no review. GitHub refuses self-approval, so without the exemption the sole
maintainer's own PRs could never qualify at all, and the argument holds at any maintainer
count — the machinery is not a boundary against its own trust root, and the author's label is
the same act of authority a self-review would be. Authorship is measured by the permission
call (`collaborators/{author}/permission`), not the PR's association field: MEMBER shifts
meaning with org base permissions and CONTRIBUTOR names a former stranger.

One enforcement point: the review check runs at gate entry, after the live-label read and
before any rebase or mode computation, on every non-idle wake including mode=reuse. The
anchor thus never depends on where a tested marker was minted (pre-anchor markers, as-is
runs), future modes inherit the check instead of remembering it, and a refusal costs no git
work. The reuse path is content-safe either way — identical bits were vetted, and commit
metadata does not execute — so the check buys architecture, not security, and costs one API
read.

Refusal mode: strip the approval labels, post the fixed teaching comment (exact wording lands
with implementation, static text, nothing from the PR), and fail the gate job red. A failed
run notifies the maintainer who triggered it, the labeler, where a green idle notifies nobody;
red distinguishes refusal from idling; and the strip keeps its green idle because it is
lifecycle (a push, nobody erred) where the refusal is a violated precondition. No deadlock:
label removal fires no wake, so the repair is self-propelling — leave the review, click the
label, and the click is the wake. Contributor-docs ripple: the canonical docs teach "a
maintainer reviews your code, then labels it."

## Decision: the cache-save doctrine (OQ6)

The rule is a sentence, not a list: **pull-request runs restore, push runs save.** The
event-name check OQ3 stamped into the setup composite is that sentence's current spelling,
not a second law beside it. A future event classifies by shape — pull-request-shaped
restores, push-shaped saves, neither-shaped restores by default — and the classification
sanctions the code change rather than a list edit deciding it. "Preflight is the only
saver" is superseded: the savers are the push-triggered passes, whose writes land in the
default-branch cache scope every PR run restores from. No opt-out exists (the toggle died
with OQ3) and none returns without amending this doctrine — a cold-start test (does the
repo install from an empty cache) is the one named exception, and getting it means
reopening the sentence, not adding a flag beside it.

## Decision: the planning reconciliation

Three independent planning passes over this record, the current repo state, and the samples
surfared defects; the corrections are rulings. The passes also converged on one factual
adjudication: the current checkout pin already carries the v7 guard (verified against the
pinned commit's own diff), so the OQ5 waiver functions without a pin bump.

1. **Secret bindings are channel-keyed.** A jobs: entry's `secrets` map is keyed by target
   channel (`pr`, `dev`, `stable`), each channel's map validated bidirectionally against
   the slots the stage declares, so exactly one keystore quartet reaches any context: the
   CI quartet under `pr` and `dev`, the production quartet under `stable`. The flat
   eleven-line map the samples show would have forwarded the production keystore into
   PR-context build jobs, breaking D6 and this ADR's own recorded residual.
2. **Self-mode spelling.** When the target repository is the toolkit itself, the generator
   emits `$/` self-repository refs, never full SHAs — OQ8's fixed-point reasoning extends
   from header stamps to `uses:` refs — and writes the underscore-prefixed lane files
   (`_integrate.yml`, `_preflight.yml`, `_retry.yml`, `_cleanup-pr-releases.yml`), no
   `release.yml` (this repo publishes nothing).
3. **The fixed spine gains a mirror slot.** Topology: gate, preflight, [mirror], fan,
   release-pr-builds, terminal — the mirror slot present exactly when the consumer's jobs:
   map carries a mirror entry, with the generator stamping the fan's needs edges
   accordingly. Provisioning precedes consumption stays true by structure.
4. **Composition, not clobbering.** The mode gate conjoins with a stage's own `if:`
   (`mode == 'full' && (<stage condition>)`), never overwrites it, so domain-internal
   gates (the empty-envelope spells) survive splicing; `release-pr-builds` rides
   `!cancelled() && !failure() && needs.gate.outputs.mode != 'idle'`, so a
   stage-condition skip does not block the merge.
5. **Least privilege by construction.** Every generated file carries top-level
   `permissions: contents: read`; spliced jobs carry the permissions their stage declares
   (the org default is `write`, so unscoped jobs would inherit it). Stage files are valid
   `workflow_call` reusables in their home repos, giving actionlint and zizmor their native
   police surface; consumer-local `path` stages live under `.github/stages/`, which the
   lint runners scan.
6. **Schema completions.** The leaf's stage-file path defaults to the entry key with an
   explicit `file` override (visible config, no transformation); an optional `targets`
   list selects which target files an entry splices into, default all three;
   `consumer-script` moves from the reusable's `with:` to a top-level `publish.yml`
   boolean, keeping the no-Python escape; per-consumer build knobs (`unity-environment`)
   live in the consumer's domain config files, not workflow inputs; `free_disk_space`
   folds to the domain's declared default. The `--check` adoption key is the presence of
   `jobs:` in the config — the sync-contributor-docs geometry, unadopted repos
   self-skipping green.
7. **Anchor mechanics.** The stacked-pair refusal runs before the anchor
   (misconfiguration is cheaper to name than an API read); only submitted reviews count
   (`PENDING` is not a review); `submitted_at` ties break by review id, later winning.
   The sole-maintainer assumption is retired as false at the org level (default repository
   permission is `write`): latest-wins across write actors is the standing verdict rule at
   any maintainer count, exactly the rule OQ4 already records.
8. **Transition and stamp obligations.** This repo's incumbent `_integrate.yml` spellings
   gain explicit candidate refs in the same change that flips the composite's event-keyed
   default (a head checkout under the incumbent plain-`pull_request` shape would certify
   the unrebased head). The wheel stamp is universal — every PyPI package the fleet
   publishes names the minting run's head commit, written into the package's source
    directory riding the ephemeral-patch window. The sibling ADRs carry amendment notes and
    this repo's AGENTS.md is rewritten as part of integration. The samples in
    `design/stage-splicing/` predate the OQ3-OQ8 rulings and lose every conflict with
    them.
9. **The tier-one file and the shared preflight harness.** The preflight reusable serves
   the integrate chain only, its checkout spelling the explicit candidate ref — which
   also restores the incumbent plain-`pull_request` suite's candidate certification under
   the event-keyed default. The generated tier-one `preflight.yml` carries its own flat
   job emitted from the generator's template, its checkout riding the event-keyed default
   (`pull_request` → PR head), so tier one never needs `with:` threading and single-copy
   lives at the generator. The post-gate reusables (mirror, `release-pr-builds`,
   `merge-if-ready`) spell the same explicit candidate ref. Self-mode detection keys on
   the consumer root's origin remote resolving to the toolkit repository, so local runs
   work without `GITHUB_REPOSITORY`.

## Decision: the go (OQ9)

Integration is ordered. No code changed in the ruling sessions: execution is deferred to
the next session, which reads `design/stage-splicing/execution-plan.md` and implements it
linearly. The plan is pure execution — steps and verification, no rationale — produced
from this record after the reconciliation above.

## Decision: the org event policy is codified (OQ7)

The permission slip is code: an event policy in infra-github-org, reviewable and versioned
like every other org artifact, never a hand-clicked setting with no history. One rule —
allow `pull_request_target` and `pull_request` for the lane file paths (the two generated
spellings plus this repo's underscore spellings; the allowlist semantics would otherwise
kill an adopting repo's incumbent plain-`pull_request` file in the window before its
adoption merge), scoped by repository to the adopting set, which grows one repo per
adoption change. Mechanism (amended by the reconciliation below): the org policies REST
API behind a pulumi dynamic resource — no provider resource exists at the pinned
pulumi-github, verified live. Timing stands: the policy exists on the org before any repo
adopts tier two,
so no adopted repo is ever slipless, and nothing in the fleet runs the target trigger
today, so enforcement day breaks nothing current regardless of which reading of the scope
wins (the changelog and docs disagree; the wide reading is assumed). The insights review
is cut by operator ruling — the evaluate-mode report adds nothing for a two-file allowlist
whose membership the design already fixes. The enforcement date was re-verified this
session: 2026-12-02 unchanged, both brownouts past.

## Decision: the emitter's determinism contract (OQ8)

The generator is deterministic by contract: same inputs, byte-identical output, every time —
the drift check is one equality comparison, and any self-inflicted reshuffle or reformat
would drown real drift in noise. The obligations: the YAML 1.1 `on:` boolean trap is pinned
in the serializer (the key stays the string `on` through write and re-read); keys and lists
emit in one stable order; a regeneration colliding with committed changes is resolved by
regenerating and taking the output, never hand-merging (hand edits to generated files
already fail the merge); golden-output tests assert byte equality so any accidental
output-shape change fails before shipping. The generated header carries no stamps — no
generator SHA, no config hash — by operator ruling: git blame names the producer, `--check`
proves the match, and no one verifies embedded hashes by eye. A stamped generator SHA also
carries a fixed-point defect: the toolkit regenerates its own files, and a file cannot
contain the SHA of the commit that contains it, so the drift check would run permanently
red. What the header carries instead is one constant warning line — generated, do not hand
edit, regenerate instead — never changing, carrying no identity, its job being the stranger
who opens the file before hand-editing it.

## Rejected alternatives

- **Closed-spine orchestrator (`certify.yml`) + certificate protocol**: preserved
  hand-authoring by moving proof across the `uses:` wall (witness jobs, merge-bot-only
  certificate ref namespaces, polling terminals). Subsumed and deleted by generation: with
  flat emitted jobs, native `needs` edges are platform-enforced and the emitter writes them
  correctly once. The certificates were the price of refusing the compiler.
- **GitHub's native merge queue as substitute**: `merge_group` runs execute the workflow file
  from the merge-group commit — including the PR's own workflow edits — with full secrets (four
  independent third-party sources, two with 2026 empirical verification; GitHub's docs are
  silent on the provenance). The enqueue click is the human act: same trust family as our
  label, with worse file provenance than ours.
- **The GitHub Security Lab two-workflow artifact pattern**: untrusted-run artifacts must
  never execute in privileged contexts, so it cannot run contributor build code with secrets
  pre-merge at all, and it requires the banned `workflow_run`.
- **Secrets post-merge only (Prow/Kubernetes shape) or trusted-config confinement (Zuul
  shape)**: provable precisely by refusing the evergreen requirement; post-merge breakage on
  secret paths is the cost they accept and we do not.
- **Command-shaped label rename**: withdrawn once the review anchor landed — the review
  supplies the approval, the label names its destination, and `approved-for-*` composes
  correctly. The misnamed element is the approve button's folklore, handled in docs.
- **File-scoped zizmor config ignores**: a fleet-shared config cannot line-scope (line numbers
  differ per consumer), and base-filename ignores mask every trigger in the named files.
  Inline block-scoped acknowledges at the exact spot are strictly tighter and travel with
  the file.
- **Git-sourced domain pins in consumer locks**: mechanically sound (verified live) and
  the strongest closure (identity), but rejected by operator ruling — not the consumption
  model for Python packages; the wheel stamp buys the same guarantee at
  machinery-trust grade.
- **Wheel-borne stage descriptors (JSON package data validated by a toolkit schema) and
  stage-emission functions (domain Python returning the job graph)**: both drafted and
  rejected within the follow-up session — each is a parallel model of GitHub Actions
  syntax, so every future Actions feature becomes toolkit schema work; direct YAML plus
  mechanical splicing inherits the platform's own DSL for free.
- **Deriving the job set from lock presence and config probes**: rejected — implicit
  ("why is build-unity running?"), and the consumer explicitly states the jobs it
  needs; the destination is a generator with no domain knowledge to derive from.
- **Generator-side secret vocabularies (canonical slot maps, then an upper-snake naming
  fallback)**: rejected as opaque — the generated output depended on transformations
  appearing in no consumer-owned file, and typo'd slots resolved silently to empty
  bindings; explicit bidirectionally-validated bindings replace them.
- **Advisory jobs (`gates: false`)**: cut — no fleet need exists, tier one is the
  feedback-only surface, and a generator stamping one uniform shape is structure over
  optionality.
- **The exact-word save list (push as an enumeration)**: behaviorally identical today, but
  every future event defaults to no, the failure is silent staleness, and the fix is a
  toolkit release plus a fleet re-pin. Rejected for the same reason the design carries no
  other lists — class rules and named contracts only.
- **The no-opt-out vow (every push-triggered setup saves, exceptions forbidden)**: buys
  nothing the sentence does not already give — the toggle is dead, so saving is already
  ambient — and permanently forecloses the cold-start test. The sentence covers the same
  ground with judgment still available at honest ambiguity.
- **Flat secret bindings (one slot map serving every channel)**: forwards the production
  keystore into PR-context build jobs, breaking D6 and this record's CI-keystore residual
  — channel-keyed bindings replace it.
- **Hand-clicked org settings (the policy configured in the UI, not codified)**: no
  history, no review gate, silently driftable — rejected; org state lives in
  infra-github-org or it is not org state.
- **The stamped header (generator SHA plus config hash per generated file)**: rejected —
  git blame already names the producer, `--check` already proves the match, and the
  generator-SHA stamp is a fixed-point defect under self-regeneration (a file cannot
  contain the SHA of the commit that contains it). One constant warning line replaces it.
- **Plain git plumbing for the gate's head fetch**: mechanically sound (the toolkit-clone
  shape, verified live, no credentials) and invisible to the guard by the vendor's own
  scoping — but that invisibility is the defect: a fetch that always rode the official
  tool would move into bash solely to dodge the check, and the acceptance would vanish
  from the audit surface the vendor built for it.

## Next session protocol

The remaining open questions are worked through as an operator interview, and the protocol is
part of this record. First: read `/workspace/response-style-guide.md` and apply it to every
response — the operator's standing complaint is jargon-dense walls that confer no meaning;
every question gets its context rebuilt from zero in plain words, assuming no prior mechanics.
The session's first act is not a question: it is a primer building the operator's mental model
of every recent or imminent GitHub platform change bearing on this design, irrespective of
any decision — the event-policy enforcement clock, the checkout tool's fork guard, the
read-only cache tokens, the review-event routing — organized as one narrative (what GitHub is
tightening, why, and what it means for anyone running a stranger's code with secrets), drawn
from Platform facts on record and re-verified where a date is involved. The primer is expected
to retire OQ5's context debt; that question stays last on the agenda either way. Then the
interview resumes: one question at a time, never advancing past an unresolved question, no
question tool, options and tradeoffs with a stated lean, and each ruling recorded here as its
own prose commit. A ruling means an ADR update and nothing else — no code changes until the
operator explicitly orders them.

## Decision: the gate's fork-head fetch takes the documented waiver (OQ5)

The checkout composite spells `allow-unsafe-pr-checkout: true` as a constant on its
`actions/checkout` step. The guard's own matching scopes the waiver: it bites only for a
trusted event plus a fork PR plus a fork-head spelling, which in this fleet is exactly the
gate job's one sanctioned fetch — candidate-ref checkouts and tier-one runs never trip the
guard, waiver or not. No new input, no toggle. The git-plumbing door was rejected: this
fetch has ridden the official tool from day one, so moving it would be a change made only
to dodge a safety check, hiding the acceptance in bash where no auditor looks instead of
in the flag the vendor built to be found. The long-term rationale does not live
here — it lives as a comment directly at the
waiver site in the composite, self-contained by the standing cold-reader rule, and is a
sanctioned exception to the comment-minimality clause (operator ruling): the comment runs
as long as the rationale needs. The acceptance is otherwise recorded the way the trigger
exception is: deliberate, on the record, mirrored by the org event policy.

## Platform facts on record (verified this session)

- `pull_request_target` and `pull_request` expose identical 21-type activity lists; neither
  contains review submission. Reviews route to `pull_request_review` (untrusted class: the PR
  merge-commit's workflow file, fork runs secretless with a read-only token). No
  `pull_request_target_review` exists; `pull_request_target` is not even a distinct webhook
  event.
- `review_requested` / `review_request_removed` are valid `pull_request_target` types and
  manual review requests require write access — but CODEOWNERS auto-requests are
  author-inducible, so the type can never serve as a permission wake.
- Labels apply to the head current at click time and carry no commit identity; reviews record
  `commit_id`. The push-then-label blind spot is real and uncovered by the strip and lease.
- The default event policy blocking `pull_request_target` in public repos: GA of workflow
  execution protections 2026-09-17 (actor rules, event rules, workflow-file targeting, free on
  all plans), brownouts 2026-11-09 and 2026-11-16, enforcement 2026-12-02; escape via an
  explicit org event policy scoped by workflow file.
- `actions/checkout` v7.0.0 (2026-06-18) blocks fork-head checkouts in
  `pull_request_target` and `workflow_run` contexts unless `allow-unsafe-pr-checkout: true`;
  older SHA pins predating the backports (2026-07-20) carry no protection at all.
- 2026-06-26: untrusted-trigger runs hold read-only cache tokens for the default-branch scope;
  saves fail with a warning.
- 2025-12-08: `pull_request_target` always reads the workflow file and `GITHUB_SHA` from the
  default branch regardless of the PR's base branch.
- `merge_group` provenance (merge-group commit's workflow files, secrets available) rests on
  four consistent third-party sources including GitHub's own docs-internal repo's indirect
  confirmation; GitHub's documentation does not state it. If the merge queue is ever
  reconsidered, verify empirically first.
- zizmor 1.30.1 inline ignores (`# zizmor: ignore[rule-id]`) work in workflow files; the
  ignore scope is the finding's span — for `dangerous-triggers`, the `on:` block.
- Fleet consumer locks carry the domains as PyPI registry sources, not git revs (placeframe
  `uv.lock`: `unity-devkit 0.3.5.dev257` and `boatyard 0.9.7`, both
  `source = { registry = "https://pypi.org/simple" }`); domain deps sit in the consumer's dev
  group only, so a git-source switch changes no published metadata.
- No version→commit mapping exists for the versions consumers actually lock: dev prereleases
  create no git tags and PyPI records no commit; only stable releases carry per-package tags
  (`unity-devkit-v0.3.4` exists; `unity-devkit-v0.3.5.dev257` has no tag to point at). A
  `uses:` ref on a tag would anyway violate the SHA law, so tag-based pinning is doubly dead.
- Verified live this session: `[tool.uv.sources]` git-pinning a workspace-member subdirectory
  (`unity-devkit = { git = ..., subdirectory = "packages/python/unity-devkit", rev = <sha> }`,
  hatchling backend) resolves with `uv lock`, and the lock records the commit as
  `source = { git = "...&rev=<sha>#<sha>" }` — generator-parseable. Recorded to establish
  that the later rejection (see rejected alternatives) was preference, not mechanical
  impossibility.
- `uses:` refs cannot carry context expressions (long-established platform behavior, already
  repo-documented for the self-test clone) — a reusable cannot receive another repository's pin
  as an input; every cross-repo `uses:` pin inside a file is static and owned by that file's
  repository.

## Accepted costs

1. Review then label for contributor PRs, two deliberate clicks; the sole maintainer's own
   PRs ride the label alone (GitHub refuses self-approval, and the machinery is not a
   boundary against its own trust root).
2. Generated files in git: re-synth on conflict, doctrine comments live in the generator not
   the output, debugging reads generated YAML.
3. The emitter becomes the most load-bearing artifact in the repo; its schema is public API
   and its discipline (leaves, fixed fan) is a permanent obligation.
4. Consumer config carries explicit channel-keyed secret bindings (the unity quartets per
   channel) — verbosity accepted for visibility and loud bidirectional validation.
5. This repo operates a vendor-warned pattern under an explicit exception (org event policy),
   with the D6 secrets residual and the operator as trust root — recorded, not hidden.
6. The domain wheel stamp is machinery-minted correspondence trusted by the generator; its
   only writers are the release pipeline and trusted publishing.
