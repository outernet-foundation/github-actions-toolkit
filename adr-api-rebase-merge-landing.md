# ADR: merge through the pull-request merge API — the forge replays the certified commits

Status: accepted — replaces the merge tail recorded in `adr-integrate-rerun-lander.md` (its
rerun/retry halves stand unchanged) and supersedes the head-sync merge sequence of
`adr-merge-gate-auto-rebase.md`. Fork PRs are out of scope — superseded 2026-11-21 by
`adr-fork-contribution-lane.md` (D2): the merge endpoint is fork-agnostic (proven live, D9),
fork PRs certify through the two-tier lane exactly as member PRs do, and the follow-up rulings
below record the self-consumption and the fork-free candidate spelling as they stood.
Date: 2026-11-19.

## Context

The rerun merge system certified "the exact SHA that merges" by force-pushing the tested rebased candidate
back onto the PR head (the head sync) and merging `--no-ff` into dev locally. Two defects:

1. **The head sync is fork-impossible.** No base-repo credential can write a fork's branch —
   platform physics, the same wall that made Mergify remove their fork-rebase impersonation
   (September 2026). The design was fundamentally fork-incompatible.
2. **The head sync is also a wart on its own terms:** the one sanctioned rewrite of a human branch,
   existing purely so GitHub's PR bookkeeping would see the merged commits on the PR's own branch.

Platform facts (verified against GitHub docs and the Mergify changelog, 2026-11):

- `PUT /repos/{owner}/{repo}/pulls/{N}/merge` with `merge_method: rebase` replays the PR's commits
  onto the base branch **server-side**: writes only the base repo, never the fork, works for any PR
  a base-repo credential can merge, and marks the PR **Merged** with full attribution. The `sha`
  parameter refuses the call (409) if the PR head moved — a machine-enforced lease.
- The merged commits are minted by GitHub at merge time: same trees, messages, authors, and order
  as a locally-tested rebase onto the same tip, but new SHAs (committer identity and timestamps
  differ). The exact merged SHAs are unknowable in advance.
- The API has **no compare-and-swap on the base**: if dev moves between the terminal's check and
  the call,   the API silently rebases onto the newer tip and merges a combination nothing tested.
  (GitHub's own merge queue had a 4.5-hour silent-wrong-merge incident in April 2026 — this
  race class is real.)
- Job-level concurrency groups with `queue: max` (2026) give a repo-wide FIFO queue that queues
  pending jobs (up to 100) instead of canceling them — and the `evergreen-dev` ruleset's sole
  bypass actor is the merge bot, so the machinery's terminals are the only writers of dev.

## Decision

Merging becomes a single API call; CI writes no commit and no human branch.

```
terminal merge job (success-gated, under the global merge queue:
                   concurrency group `merge`, queue max, on the calling job — lint-enforced):
  policy prefix unchanged (closed PR quiet exit, label absent quiet exit,
                          head-moved lease abort, dev-moved retry dispatch, attempt bound)
  merge:
    tag refs/tags/certified/{N} at the tested candidate X        (the release weld's key)
    PUT /pulls/{N}/merge  merge_method=rebase  sha={lease}       (GitHub replays onto dev itself)
    verify: the merged dev tree equals X's tree                  (the race alarm)
    delete candidate ref + head branch, sweep pr-{N}-*, promote       (unchanged)
```

Elements and their laws:

- **No CI write to any human branch.** The head sync is deleted. The candidate ref
  `refs/heads/candidate/{N}` is the only branch CI pushes before the merge; the merge itself is
  GitHub's.
- **CI creates zero commits.** The merged commits are the forge's replay; dev's `--no-ff` bubble
  dies and dev becomes fully linear; `dev` → `main` stays a true fast-forward. The evergreen-dev
  ruleset's `required_linear_history` becomes literally true of bot merges.
- **Evergreen, restated:** nothing merges whose *tree* was not certified green on the exact dev tip
  it merges against. The SHA-exact letter is unreachable through any fork-capable mechanism — the
  forge mints the merged SHAs — and the tree was always the invariant; the SHA was its proxy. Every
  artifact still keys at our SHA `X` through the certified tag.
- **The certified tag is the release weld's key.** After an API rebase merge the PR head is the
  unreplayed original and dev's tip is the forge's mint — neither equals `X`. `refs/tags/certified/{N}`
  carries `X` to the dev/stable release runs (tags ride the delivery checkout's tag fetch); the
  release prefers it and falls back to the PR head. Tags accumulate one per merged PR, the same
  order as per-package version tags, and are never deleted.
- **The race is owned code:** the merge queue serializes the terminals (the only writers of dev);
  the terminal's dev-moved `is-ancestor` check inside the queued job is the compare; the
  post-merge tree verify is the alarm. A refusal from the API is mapped by re-reading live state
  (head moved → re-poke; dev moved → re-poke; anything else → loud) — gh hides the HTTP status
  (cli/cli#10579), so state names the branch, never the error body.
- **Fork PRs merge through this API exactly like member PRs** (superseding the original
  out-of-scope stance — `adr-fork-contribution-lane.md` D2/D9): the trusted tier's rebase job
  pushes the candidate ref itself, so nothing here depends on a fork credential; the merge
  endpoint is fork-agnostic, and every fork-impossible element of the older shapes (head sync,
  local merge push, welds keyed on a synced head) is already gone.

## Rejected alternatives

- **Keep the head sync.** The only fork-never option, and it rewrites human branches.
- **Merge-bubble lane (the bors shape):** test a merge commit carrying the original head, merge by
  fast-forward, close the PR through indirect-merge reachability. Preserves SHA-exact certification
  and full attribution, but merges unreplayed fork commits under merge bubbles and forks the
  certificate shape. The standing fallback if API-merge semantics disappoint.
- **Native merge queue for fork PRs.** Standing rejection (supply-chain D5): maximal coupling,
  certification becomes the platform's black box.
- **`merge_method: squash`.** Collapses commit identity; replayed commits preserve authorship.
- **Allow-edits fork pushes to keep the head sync for forks.** Per-PR opt-in, impossible for
   org-owned forks, the exact seam Mergify dismantled; no surveyed merge system depends on it.

## Accepted costs

1. **Tree-certified, not SHA-certified.** A doctrine amendment, not a mechanism gap: the binary
   stamps, shelf keys, and ordinals still derive at `X`.
2. **The race guard is owned code** (queue + check + alarm) where git push gave a free non-FF
   rejection. A writer outside the machinery (a manual bypass push to dev) can still race the window;
   the alarm catches it after the fact, loudly.
3. **`certified/{N}` tags accumulate** (bounded, one per PR). Non-publishing consumers accumulate
   them unconsumed.
4. **Refusal mapping costs two extra reads** (PR view, dev fetch) because gh hides the status code.
5. **Empty-commit drift:** GitHub's replay and our rebase must agree on skipping already-applied
   commits, or dev's merged count drifts from `X`'s count by the skipped commits — cosmetic; the
   ordinals derive at `X` either way.
6. **Reruns re-push the certified tag (force).** Idempotent by construction: only the merge writes
   it, and an update means a prior attempt tagged but failed to merge — the new candidate supersedes.

## Follow-up rulings, same day

1. **This repo self-consumes the merge machinery** (superseding the 2026-10-11 operator-direct ruling): its
   own `_integrate.yml` carries the consumer shape — rebase, preflight, terminal merge under the
   merge queue — through `$/` calls. The retry reusable stays `retry.yml` (beside `rebase.yml`
   and `merge-if-ready.yml`); this repo's own dispatch shim is `_retry.yml` — a shim and a reusable cannot
   share a filename, and the underscore prefix keeps them apart.
2. **Fork PRs and non-PR runs are assumed not to exist.** The `candidate-ref` verb is deleted — the
   checkout composite spells `refs/heads/candidate/{N}` directly (the rebase job has pushed it by
    `needs` order, so there is nothing to resolve); the rebase verb's cross-repository pass-through
    and the merge job's fork-refusal step are deleted with it. The fork lane, when it ships,
   reintroduces resolution (a second ref spelling plus fallback, with tests) for cases that exist
   by then — additive code, not a redesign.
3. **actionlint's concurrency schema predates the `queue` key**; the lint carries a fifth bridge
   ignore for it until the pin moves.
4. **This repo's own top-level workflows carry a leading underscore** (`_integrate.yml`,
   `_retry.yml`, `_cleanup-pr-releases.yml`), separating them from the reusables beside them —
   GitHub discovers workflows only as direct files of `.github/workflows`, so naming is the only
   separator, and the lint normalizes the prefix before contract matching. Two couplings came
   along: the merge reusable gained a `retry-workflow` input (default `retry.yml`, the consumer
   contract, threaded as `RETRY_WORKFLOW` env) so the dispatch can address the prefixed shim, and
   `_cleanup-pr-releases.yml` closes a self-consumption gap — the closed-PR sweep shim had no
   spelling here, leaving candidate refs behind on abandoned PRs.
