from __future__ import annotations

import os
import shlex
from subprocess import CalledProcessError
from typing import Annotated

import typer
from bashrun.bash import bash, bash_check, bash_output

from github_actions_toolkit.config import Settings
from github_actions_toolkit.merging import (
    AS_IS_INTEGRATE_LABEL,
    BASE_BRANCH,
    FETCH_DEV_COMMAND,
    GIT_COMMAND,
    MERGE_LABEL,
    REBASE_INTEGRATE_LABEL,
    candidate_ref,
    label_names,
    pull_request_number_from_ref,
    tested_tag,
    view_pull_request,
)

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

APPROVAL_LABELS = (AS_IS_INTEGRATE_LABEL, REBASE_INTEGRATE_LABEL, MERGE_LABEL)
SYNCHRONIZE_EVENT = "synchronize"
STRIP_COMMENT = (
    "Your push revoked this PR's approval: approval labels are granted per head."
    " A maintainer re-approves your changes by re-applying the label after review."
)


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
        strip_approval_labels(pr_number, labels)
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


def strip_approval_labels(pr_number: int, labels: set[str]) -> None:
    for label in sorted(labels & set(APPROVAL_LABELS)):
        bash(f"gh pr edit {pr_number} --remove-label {label}")
        print(f"  stripped {label} (the push revoked the approval it named)")
    bash(f"gh pr comment {pr_number} --body {shlex.quote(STRIP_COMMENT)}")
    print(f"  posted the re-approval explanation on PR #{pr_number}")

