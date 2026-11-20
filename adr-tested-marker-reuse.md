# ADR: the tested marker — a prior green run's certificate is reused when the tree is unchanged

Status: accepted — implemented on `adr-merge-gate-auto-rebase`. Amends the certificate law of
`adr-integrate-rerun-lander.md` ("the run is the certificate" — the tested marker becomes the
certificate, minted by a green run's terminal); that ADR's rerun/retry halves and the entire merge
sequence of `adr-api-rebase-merge-landing.md` stand unchanged. `adr-ci-label-modes.md` later
subsumed this ADR's `reuse` output into the `mode` output (idle|full|reuse) and rekeyed the gates
below onto `mode`; the certificate mechanics stand unchanged.
Date: 2026-11-20.

## Context

The four wakes make every run a full candidate merge, and the labeled wake is one of them: adding
`ready-to-merge` to a PR whose suite just went green starts a brand-new run that re-derives the
same candidate (same head, same dev tip — the same tree) and re-runs the entire suite to certify
what a completed run already certified. This is accepted cost 1 of the rerun-lander ADR ("every
merge pays one full suite") hitting its degenerate case: the second suite proves nothing the first
did not. placeframe-capture-tool (the dogfood consumer) surfaced it live — push → green → label →
a redundant full suite before the merge.

The rerun-lander deleted the checks-tab fast path and its law — "nothing merges on a read; the run
is the certificate" — because the photographed state was mutable, unowned, and unpinned: any
workflow's checks, a read-to-merge race on the head, no proof of what tree the checks certified.

## Decision

The certificate becomes a ref the machinery mints and re-derives:

- **The terminal stamps `refs/tags/tested/{N}` at its candidate on entry** — after the OPEN
  check, before policy. The terminal is success-gated, so the stamp is post-green by
  construction; on a reuse run the terminal's candidate already is the stamped commit and the
  re-stamp is a no-op. The merge sequence deletes the marker with the candidate ref, and the
  closed-PR sweep is the backstop for interrupted merges.
- **The rebase job probes by tree identity.** After rebasing the frozen payload head onto the
  live dev tip, it fetches the marker and compares tree hashes. Equal trees mean the exact tree
  this run would test was certified against this exact dev tip, so the suite would re-test
  identical bits. Tree identity is the whole predicate: any head push or dev movement grows a
  different tree and re-widens to a full suite — correct, because certification is base-specific.
- **Reuse preserves the certified SHA, not just the tree.** The matched rebase does not push its
  own commits: the candidate ref is (re)pointed at the marker's commit, because every weld — the
  builds shelf's `sha-{full}` keys, the `certified/{N}` tag, the commit-count ordinals — keys at
  the SHA the prior run certified. A tree-equal re-push would orphan all of them.
- **The gates are consumer-side and lint-mandated.** The rebase reusable grows one output,
  `reuse` (`workflow_call` outputs, threaded from the verb's `$GITHUB_OUTPUT` line; later
  subsumed into `mode` by `adr-ci-label-modes.md`). Every suite job in the consumer's
  `integrate.yml` carries the full-mode gate and needs the rebase job (an output reference
  requires the need, so the mirror serializes behind the rebase job — accepted). The terminal
  carries
  `if: !cancelled() && !failure() && (needs.<suite>.result == 'success' || needs.<rebase>.outputs.<output> == 'reuse')`
  — a skipped suite reaches the terminal **only** through the rebase job's proof, so no other
  skip path (a removed job, a mis-gated leg) can engineer a vacuously green terminal. The suite
  gates contain no status function and so default to `success()`: a failed or cancelled need
  still skips them, and the skipped-need cascade carries the skip through the chain to the
  terminal, whose explicit gate is the only continuation point.
- **Every merge-time guard is unchanged**: the label-is-live policy, the head lease, the global
  merge queue, the in-queue dev-moved compare, the post-merge tree verify, the refusal mapping.
  Reuse only answers "did this run need a suite at all"; it never touches how a merge happens.

Why this is not the deleted fast path: the fast path read mutable, arbitrary, unpinned state (the
checks tab) and merged on the read. The marker can only be minted by this machinery's
success-gated terminal, is pinned to an exact tree, and is re-derived fresh by each probe — and
the races the fast path ignored are guarded by the unchanged lease/queue/verify machinery.

## Rejected alternatives

- **Read the prior run's conclusion from the Actions API** (check-runs or run status): the
  photograph again — machine-reading the checks tab through the side door, resting on API state
  the machinery does not own.
- **Re-run the prior green run instead of waking fresh**: reruns re-run every job — there is no
  skip primitive — and the labeled wake fires regardless; the only question is what the woken run
  does.
- **Reuse on commit-SHA equality instead of tree equality**: a re-rebase mints new commit SHAs
  (committer timestamps) for identical trees; SHA equality would almost never fire, and matching
  on it would break the SHA-preserving rule anyway.
- **Widen the window** (reuse across dev movement by re-certifying the delta): certification is
  base-specific; the widened form is exactly the untested-combination merge the evergreen
  invariant exists to prevent.
- **Stamp from the last suite job instead of the terminal**: the terminal is the success-gated
  point; a suite-job stamp would need its own gate logic and would fork the trust point the rest
  of the machinery already stands on.

## Accepted costs

1. **The doctrine amendment itself**: "the run is the certificate" becomes "the tested marker is
   the certificate, minted by a green run's terminal" — a run is one way to mint it, a
   tree-identical probe another. This ADR reopens, narrowly and proof-carrying, the door the
   rerun-lander shut; the letter of that law does not survive it.
2. **One green is final**: reuse trusts the first green; a rerun's second sample against flaky or
   environmental failures is gone (the tree is identical, so the only thing a rerun can add is
   luck-of-the-day).
3. **The window is exactly "nothing changed"**: any push or dev movement pays the full suite.
4. **Labeling while the suite is in flight still burns a run**: the labeled wake cancels the
   in-flight run (the per-ref concurrency group) before it can stamp.
5. **More machinery in the merge path**: a new ephemeral ref grammar, the probe, the gates, and
   their lint contract.
6. **Reopened PRs re-test**: the close sweep deletes the marker with everything else, so a
   close-reopen cycle on an unchanged tree certifies again.

## Adoption

placeframe-capture-tool adopts at its pin bump: every suite job and the terminal gain the mode
gates, and `mirror-images` gains `needs: [rebase]`. A consumer that bumps the pin without the
gates keeps today's behavior — ungated suite jobs run on the kept candidate (a tree-identical
re-test) and the machinery is correct either way; the lint contract flips the gates from
optional to mandatory at the file it can see. The green-certificate reuse itself composes with
the as-is lane: a fresh PR's as-is tree equals its rebased tree, so a `ready-to-integrate` run's
marker satisfies the later `ready-to-merge` probe (see `adr-ci-label-modes.md`).
