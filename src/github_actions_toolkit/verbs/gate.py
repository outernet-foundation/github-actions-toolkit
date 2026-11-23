from __future__ import annotations

import os
import shlex
from subprocess import CalledProcessError
from typing import Annotated

import typer
from bashrun.bash import bash, bash_check, bash_output
from pydantic import BaseModel, RootModel

from github_actions_toolkit.config import Settings
from github_actions_toolkit.merging import (
    AS_IS_INTEGRATE_LABEL,
    BASE_BRANCH,
    FETCH_DEV_COMMAND,
    GIT_COMMAND,
    MERGE_LABEL,
    REBASE_INTEGRATE_LABEL,
    WRITE_PERMISSIONS,
    ActorEntry,
    author_permission,
    candidate_ref,
    label_names,
    pull_request_number_from_ref,
    tested_tag,
    view_pull_request,
)

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

APPROVAL_LABELS = (AS_IS_INTEGRATE_LABEL, REBASE_INTEGRATE_LABEL, MERGE_LABEL)
SYNCHRONIZE_EVENT = "synchronize"
APPROVED_REVIEW = "APPROVED"
PENDING_REVIEW = "PENDING"
STRIP_COMMENT = (
    "Your push revoked this PR's approval: approval labels are granted per head."
    " A maintainer re-approves your changes by re-applying the label after review."
)
ANCHOR_COMMENT = (
    "This PR's approval labels were removed: no maintainer's approving review stands at its"
    " current head. A maintainer approves the latest commit through a review, then applies the"
    " approval label again. The label is what starts the run."
)
REVIEW_REPAIR = "A maintainer approves the latest commit through a review, then applies the label again"


class ReviewEntry(BaseModel):
    id: int
    state: str
    commit_id: str
    submitted_at: str | None
    user: ActorEntry


# Parse one inner list per page, the shape gh api --paginate --slurp prints
class ReviewPages(RootModel[list[list[ReviewEntry]]]):
    root: list[list[ReviewEntry]]


@app.command()
def main(
    dry_run: Annotated[
        bool, typer.Option(help="Exercise the full machinery and report, with zero side effects")
    ] = False,
) -> None:
    settings = Settings.model_validate({})
    pr_number = pull_request_number_from_ref(settings.github_ref)
    pull_request = view_pull_request(pr_number)
    labels = label_names(pull_request)
    candidate_branch = candidate_ref(pr_number)

    stripping = settings.pr_event_action == SYNCHRONIZE_EVENT and not labels.isdisjoint(APPROVAL_LABELS)
    # If a synchronize wake arrives under a live approval label
    if stripping and dry_run:
        print(f"  would strip {sorted(labels & set(APPROVAL_LABELS))} from PR #{pr_number} and idle")
        emit_mode_output("idle")
        return
    if stripping:
        strip_approval_labels(pr_number, labels, STRIP_COMMENT)
        pull_request = view_pull_request(pr_number)
        labels = label_names(pull_request)

    stacked = AS_IS_INTEGRATE_LABEL in labels and (REBASE_INTEGRATE_LABEL in labels or MERGE_LABEL in labels)
    contradiction = (
        f"PR #{pr_number} carries {AS_IS_INTEGRATE_LABEL} together with {REBASE_INTEGRATE_LABEL}"
        f" or {MERGE_LABEL}: the as-is branch never rebases and never merges. Remove"
        f" {AS_IS_INTEGRATE_LABEL} to enter the rebase path, or drop the rebase-path label"
        f" for as-is CI"
    )
    # If the as-is label stacks on a rebase-path label
    if stacked and dry_run:
        print(f"  would abort: {contradiction}")
        return
    if stacked:
        raise SystemExit(contradiction)

    # If no approval label is live
    if labels.isdisjoint(APPROVAL_LABELS):
        print(
            f"  no CI label on PR #{pr_number}, idling (apply {AS_IS_INTEGRATE_LABEL} for as-is CI"
            f" or {REBASE_INTEGRATE_LABEL} / {MERGE_LABEL} for the rebased path)"
        )
        emit_mode_output("idle")
        return

    # Let a write actor's own PR ride the label alone, because GitHub refuses self-approval
    anchored = author_permission(pull_request.author.login) in WRITE_PERMISSIONS
    verdict: ReviewEntry | None = None
    head = ""
    if anchored:
        print(f"  {pull_request.author.login} holds write permission, so the label alone anchors PR #{pr_number}")
    if not anchored:
        head = bash_output("git rev-parse HEAD").strip()
        pages = ReviewPages.model_validate_json(
            bash_output(f"gh api repos/{settings.github_repository}/pulls/{pr_number}/reviews --paginate --slurp")
        )
        submitted = [
            review
            for page in pages.root
            for review in page
            if review.state != PENDING_REVIEW and review.commit_id == head
        ]
        # Count only write actors' reviews, because strangers can review a public repository
        write_actors = {
            review.user.login for review in submitted if author_permission(review.user.login) in WRITE_PERMISSIONS
        }
        verdict = max(
            (review for review in submitted if review.user.login in write_actors),
            key=lambda review: (review.submitted_at or "", review.id),
            default=None,
        )
    if verdict is not None and verdict.state == APPROVED_REVIEW:
        print(f"  {verdict.user.login} approved head {head[:12]}, the review anchors this run")
    refused = not anchored and (verdict is None or verdict.state != APPROVED_REVIEW)
    refusal = (
        f"PR #{pr_number} carries an approval label but no write actor has reviewed head {head[:12]}"
        if verdict is None
        else (
            f"PR #{pr_number} carries an approval label but the latest write-actor review at head"
            f" {head[:12]} is {verdict.state}"
        )
    )
    # If no approving review stands at the checked-out head
    if refused and dry_run:
        print(f"  would refuse: {refusal}. {REVIEW_REPAIR}")
        print(f"  would strip {sorted(labels & set(APPROVAL_LABELS))} from PR #{pr_number} and post the explanation")
        return
    if refused:
        strip_approval_labels(pr_number, labels, ANCHOR_COMMENT)
        raise SystemExit(f"{refusal}. {REVIEW_REPAIR}")

    if AS_IS_INTEGRATE_LABEL in labels and dry_run:
        print(f"  would push the head as-is as {candidate_branch}")
        emit_mode_output("full")
        return
    if AS_IS_INTEGRATE_LABEL in labels:
        bash(f"{GIT_COMMAND} push origin +HEAD:{candidate_branch}")
        print(f"  pushed the head as-is as {candidate_branch}")
        emit_mode_output("full")
        return

    bash(FETCH_DEV_COMMAND)
    if dry_run:
        print(
            f"  would rebuild PR #{pr_number} onto the {BASE_BRANCH} tip, probe the tested"
            f" marker for reuse, and force-push {candidate_branch}"
        )
        return

    # Author the rebased commits as the merge bot
    bash('git config user.name "merge-bot"')
    bash('git config user.email "merge-bot@users.noreply.github.com"')

    # Rebase the PR onto the current dev tip and abort with the conflicted paths on conflict
    merge_base = bash_output("git merge-base FETCH_HEAD HEAD").strip()
    try:
        bash(f"git rebase --onto FETCH_HEAD {merge_base} HEAD")
    except CalledProcessError:
        # Collect the conflicted paths before the abort clears them from the index
        conflicted = bash_output("git diff --name-only --diff-filter=U").strip()
        bash("git rebase --abort")
        raise SystemExit(
            f"rebasing onto {BASE_BRANCH} conflicts. Rebase the PR locally and push the result:\n{conflicted}"
            f"\nFor CI on the branch as-is instead, swap to the {AS_IS_INTEGRATE_LABEL} label"
        ) from None

    # If a tested marker's tree matches this rebase
    tag = tested_tag(pr_number)
    marker = bash_check(f"{GIT_COMMAND} fetch origin +refs/tags/{tag}:refs/tags/{tag}")
    rebased_tree = bash_output("git rev-parse HEAD^{tree}").strip() if marker else ""
    tested_tree = bash_output(f"git rev-parse refs/tags/{tag}^{{tree}}").strip() if marker else ""
    if marker and rebased_tree == tested_tree:
        tested_oid = bash_output(f"git rev-parse refs/tags/{tag}").strip()
        bash(f"{GIT_COMMAND} push origin +{tested_oid}:{candidate_branch}")
        print(f"  reuse: {candidate_branch} keeps the tested candidate {tested_oid[:12]}, the rebased tree unchanged")
        emit_mode_output("reuse")
        return
    bash(f"{GIT_COMMAND} push origin +HEAD:{candidate_branch}")
    print(f"  force-pushed {candidate_branch}")
    emit_mode_output("full")


def emit_mode_output(value: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as file:
            file.write(f"mode={value}\n")
        return
    print(f"mode={value}")


def strip_approval_labels(pr_number: int, labels: set[str], comment: str) -> None:
    for label in sorted(labels & set(APPROVAL_LABELS)):
        bash(f"gh pr edit {pr_number} --remove-label {label}")
        print(f"  stripped {label}")
    bash(f"gh pr comment {pr_number} --body {shlex.quote(comment)}")
    print(f"  posted the explanation on PR #{pr_number}")
