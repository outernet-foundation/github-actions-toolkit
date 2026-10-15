# Plan: dev cache promotion at merge + unbuffered CI verb output

Designed 2026-10-15 in session with the operator, out of an investigation of
placeframe-capture-tool's build-unity CI leg. All design points below are
OPERATOR-RULED; the execution session should not re-litigate them. Point 4 of
the older `plan-unity-verb-contract.md` ("New PRs get no fallback cache") is
SUPERSEDED by this plan: PR first builds now fall back to the dev cache.

## Context (evidence)

- The unity-library cache key is `cache_key(project, platform, pr_number)` =
  `{name.lower()}-{platform}-pr-{N}` (no PR → `-dev`), so the first build of
  every PR is cold. Cold run measured at ~21 min editor time, dominated by
  IL2CPP C++ compilation (~13 min, one bee progress line per ~50 s) — those
  `Library/Bee` artifacts cache-hit when a Library is restored.
- Nothing refreshes the dev tag. Tags observed on
  `ghcr.io/outernet-foundation/placeframe-capture-tool/cache/unity-library`:
  `capturetool-AndroidMobile-pr-7`…`pr-12` (fresh per-PR), `…-dev` dated
  2026-09-30 (15 days stale — only a manual `workflow_dispatch` builds with an
  empty PR number), legacy `…-main` 2026-09-28.
- Verb prints are invisible in real time: python stdout is block-buffered when
  piped. In run 38805015490 the `Cache miss: unity-library` / `Cache hit:
  unity-upm` lines (events of 20:53) carry timestamps of 21:14:43 — flushed at
  process exit, after the whole build.

## Ruled design

1. **Unbuffer via workflow env, not entrypoints.** `PYTHONUNBUFFERED: "1"` in
   this repo's workflow files. Rationale: the buffering victims include
   build-artifact-registry, a library with no entrypoints — env in the binding's
   YAML reaches every verb process and every library it imports; entry-point
   `reconfigure` would mean ~5 packages, 5 publishes, 5 relocks. bashrun is the
   wrong layer (it wraps child shells; the parent's prints never pass through).
   Local terminal runs are already line-buffered; nothing is lost.
2. **PR restore falls back `pr-N` → `dev` → miss.** `cache.restore()` in
   build-artifact-registry already takes `fallback_tags`; the unity build verb
   just never passed any.
3. **The dev tag refreshes at merge time, by aliasing, inside `merge_gate.py`.**
   Under the bors model (gate requires rebased-onto-dev + all-green at the
   certified head; merge is `--no-ff` of a head that already contains dev), the
   merge commit's tree equals the PR head's tree — so `pr-N`'s library cache at
   merge is exactly the library of the new dev head. Zero staleness by
   construction. Alias-at-save was rejected: it could promote a never-landed
   PR's library over a landed one.
4. **Best-effort promote, Warn-not-fail.** A landed PR must never render a
   failed gate. Failure degrades to the previous dev cache (next PR slightly
   colder, never broken) and self-heals at the next landing. Not re-runnable
   post-merge (the gate refuses non-OPEN on re-run); manual `oras tag` is the
   escape hatch.
5. **Named contract (precedent: the leg schema).** The library cache OCI
   repository is `{registry}/cache/unity-library`; the tag grammar is
   unity-devkit's `identity.cache_key` — `{project.lower()}-{platform}-{scope}`,
   `scope = pr-{N} | dev`. The binding implements a suffix-swap promotion
   (`-pr-{N}` → `-dev`, same digest, `oras tag` — metadata alias, zero
   re-upload, no extra storage). A grammar change in unity-devkit must update
   the binding's matcher and both repos' AGENTS.md.
6. **Doctrine amendment:** the merge-gate job's permissions become
   `contents: read` + `packages: write` (was contents-read-only, "every write
   rides the App token"). The App has no known packages grant; GITHUB_TOKEN via
   the neutral `REGISTRY_*` chain is the auth path.
7. **Heartbeat in `run_unity_batchmode` is DEFERRED — do not add it.** Same for
   a post-run phase summary: out of scope.

## Work items (dependency order)

### 1. build-artifact-registry (publishes first)

- `src/build_artifact_registry/cache.py`: new primitive — list a cache
  repository's tags, retag every tag ending `-pr-{N}` (exact PR number, tags
  preserve case) to the `-dev` spelling via `oras tag`. Suggested shape:
  `promote_scope(registry, name, pr_number) -> list[str]` returning the promoted
  tags. ORAS CLI knowledge lives only in this package. Additive → patch-auto
  (manual `major_minor` bumps are for API breaks only).
- Publish via its release flow.

### 2. github-actions-toolkit (this repo)

- `src/github_actions_toolkit/verbs/merge_gate.py`: after the dev push, alongside
  branch deletion / release sweep, promote via the new primitive —
  best-effort: catch bashrun's `CalledProcessError` (specific, exogenous), print
  a warning naming the missed promotion, continue. Add a "would promote cache
  tags for pr-{N}" line to `report_dry_run` so preflight's self-certification
  exercises it.
- `.github/workflows/merge-gate.yml` (reusable): thread step env
  `REGISTRY: ghcr.io/${{ github.repository }}`,
  `REGISTRY_TOKEN: ${{ github.token }}`, `REGISTRY_USERNAME: ${{ github.actor }}`
  on the verb step (build-artifact-registry's neutral chain reads these; it does
  not read GITHUB_TOKEN ambiently).
- `PYTHONUNBUFFERED: "1"` at top-level `env:` in every reusable under
  `.github/workflows/` that runs python verbs; per-step `env:` in the release
  composite (composites cannot set workflow-level env).
- Relock this repo's `uv.lock` to pick up the new build-artifact-registry
  release (the merge-gate verb runs from this checkout with `--locked`).
- AGENTS.md, spec-first, prose commit separate from code: amend the merge-gate
  permissions doctrine (point 6 above); document the named contract (point 5).

### 3. unity-devkit (independent of item 2; proceed in parallel)

- `packages/python/unity-devkit/src/unity_devkit/build_unity.py`: the CI shape's
  library restore gains
  `fallback_tags=[cache_key(project, platform, None)]`.
- AGENTS.md: note the cache grammar is now a cross-repo named contract with the
  binding.
- Publish via its release flow (path-diff gated).

### 4. placeframe-capture-tool (last)

- The workspace checkout has an unresolved local merge on `integrate.yml`,
  `merge-gate.yml`, `release.yml` (the 33846e0 ↔ 12fa3162 repin conflict) —
  resolve that first; everything here rides a clean repin.
- Repin every `uses:` ref to the new toolkit SHA (one SHA repo-wide, lint
  enforced); the merge-gate job's permissions gain `packages: write`; relock
  the dev group for the new unity-devkit.

## Ordering constraints

- build-artifact-registry publish → this repo's relock (its locked env resolves
  the primitive from PyPI).
- This repo's push (operator-owned) before any consumer repin — the pinned SHA
  must exist on the remote before consumer CI runs.
- unity-devkit publish before the consumer relock.
- Prose and code in separate commits; no trailers; subjects under 72 chars.
- Pushes/PRs are operator-owned everywhere: hand over branch + SHA, never push.

## Verification

- New-PR integrate run: `Cache hit/miss`/`Falling back` lines appear at restore
  time (unbuffered proof); once a dev alias exists, expect
  `Falling back to unity-library:…-dev` then `Cache hit`, and an IL2CPP phase
  in minutes rather than ~13 (for a PR with light code deltas off fresh dev).
- After the first landing under the new gate (token with Packages:read, then
  `oras login ghcr.io` + `oras manifest fetch …/cache/unity-library:capturetool-AndroidMobile-dev`):
  the `org.opencontainers.image.created` annotation matches the merge time, not
  2026-09-30.
- This repo's own preflight self-certification (`merge-gate --dry-run`) prints
  the promote line.

## Current state at handoff

- github-actions-toolkit: clean, on `dev` @ 33846e0.
- placeframe-capture-tool: workspace mid-merge (UU on three workflow files);
  PR #12 landed remotely as fc7b1fc.
- Sandbox notes for verification: `GH_TOKEN=$(uv run mint-github-app-token) gh …`
  (Packages:read); `oras` at `~/.local/bin/oras`; never `gh run watch`.
