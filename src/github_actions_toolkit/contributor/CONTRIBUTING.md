# Contributing

## Opening a pull request

- Pull requests target the `dev` branch — never `main`.
- Anyone may open a pull request, from a fork or from a branch of this repository.
- Keep the pull request small and give it a clear title and description: they become the
  release notes.

## What runs after you open

- A secretless advisory check runs automatically on your pull request's head whenever it is
  opened or pushed. First-time contributors' runs wait for a one-time maintainer approval
  before they start — that click is GitHub's, not this project's.
- Beyond that advisory check, CI is human-paced: nothing expensive runs until a maintainer
  acts.

## Approval

- Approval is two clicks from a maintainer: a review of your code (GitHub's Approve button),
  then an `approved-for-*` label. The review is the approval. The label is the command that
  tells CI what to do with the approved commit.
- A green approve check means a maintainer has vetted that exact commit. It does not mean the
  pull request merges.
- Both the review and the label attach to one commit, the pull request's current head:
  - pushing more commits revokes approval: the label is removed automatically, and a
    maintainer reviews the new commits, then labels the pull request again;
  - closing and reopening, or marking a draft ready for review, keeps the approval standing.
- If a label lands on a commit no maintainer has approved, CI removes the label, leaves a
  comment explaining why, and shows a red check. Nothing is wrong with your code: a
  maintainer approves the current head and applies the label again.

## When a check is red

- A real failure with a fix on your side: push the fix. The push revoked approval, so the
  maintainer reviews the change, then re-approves.
- A flaky failure: the run can be re-run. The review and the label are untouched and the
  approved head is retested.
- Merge conflicts: rebase onto `dev` and push.

## Builds and prereleases

- Every approved pull request publishes a public prerelease build, signed with the CI key and
  carrying a suffixed application identity (for example `.pr123`). These prereleases install
  beside production builds and beside dev builds without conflicts.
- Our machinery never writes to your branch. Merges are performed by the forge and your
  commits keep their authorship.
