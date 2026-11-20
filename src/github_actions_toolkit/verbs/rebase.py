from __future__ import annotations

import os
from subprocess import CalledProcessError
from typing import Annotated

import typer
from bashrun.bash import bash, bash_check, bash_output

from github_actions_toolkit.config import Settings
from github_actions_toolkit.pull_requests import (
    AS_IS_INTEGRATE_LABEL,
    MERGE_LABEL,
    REBASE_INTEGRATE_LABEL,
    label_names,
    view_pull_request,
)
from github_actions_toolkit.refs import (
    BASE_BRANCH,
    FETCH_DEV_COMMAND,
    GIT_COMMAND,
    candidate_ref,
    pull_request_number_from_ref,
    tested_tag,
)

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

CI_LABELS = (AS_IS_INTEGRATE_LABEL, REBASE_INTEGRATE_LABEL, MERGE_LABEL)


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

    # The as-is selector certifies the branch where it stands, so it cannot stack on either
    # rebase-path label — the contradictory state is refused before any suite minute burns
    if AS_IS_INTEGRATE_LABEL in labels and (REBASE_INTEGRATE_LABEL in labels or MERGE_LABEL in labels):
        refuse_contradictory_labels(pr_number, dry_run)
        return

    # No CI label means no run: the wake idles without touching any ref
    if labels.isdisjoint(CI_LABELS):
        print(
            f"  no CI label on PR #{pr_number}; idling (apply {AS_IS_INTEGRATE_LABEL} for as-is CI"
            f" or {REBASE_INTEGRATE_LABEL} / {MERGE_LABEL} for the rebased path)"
        )
        emit_mode_output("idle")
        return

    # The plain label runs the machinery on the branch as-is: the head becomes the candidate
    # with no rebase, and the terminal never merges it
    if AS_IS_INTEGRATE_LABEL in labels:
        if dry_run:
            print(f"  would push the head as-is as {candidate_branch}")
            emit_mode_output("full")
            return
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

    # Rebase the PR onto the current dev tip, aborting with the conflicted paths on conflict
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

    # A tested marker whose tree matches this rebase names a candidate a prior success-gated
    # terminal already certified against this same dev tip, so the suite would re-test identical
    # bits; the candidate ref keeps the marker's commit because the shelf, the certified tag,
    # and the commit count all key at that SHA
    tag = tested_tag(pr_number)
    if tree_matches_tested_marker(tag):
        tested_oid = bash_output(f"git rev-parse refs/tags/{tag}").strip()
        bash(f"{GIT_COMMAND} push origin +{tested_oid}:{candidate_branch}")
        print(
            f"  reuse: {candidate_branch} keeps the tested candidate {tested_oid[:12]} — the rebased tree is unchanged"
        )
        emit_mode_output("reuse")
        return
    bash(f"{GIT_COMMAND} push origin +HEAD:{candidate_branch}")
    print(f"  force-pushed {candidate_branch}")
    emit_mode_output("full")


def refuse_contradictory_labels(pr_number: int, dry_run: bool) -> None:
    reason = (
        f"PR #{pr_number} carries {AS_IS_INTEGRATE_LABEL} together with {REBASE_INTEGRATE_LABEL}"
        f" or {MERGE_LABEL}: the as-is branch never rebases and never merges. Remove"
        f" {AS_IS_INTEGRATE_LABEL} to enter the rebase path, or drop the rebase-path label"
        f" for as-is CI"
    )
    if dry_run:
        print(f"  would abort: {reason}")
        return
    raise SystemExit(reason)


def tree_matches_tested_marker(tag: str) -> bool:
    # An absent marker is the first-run case, so the failed fetch is the probe's own no-op
    if not bash_check(f"{GIT_COMMAND} fetch origin +refs/tags/{tag}:refs/tags/{tag}"):
        return False
    rebased_tree = bash_output("git rev-parse HEAD^{tree}").strip()
    tested_tree = bash_output(f"git rev-parse refs/tags/{tag}^{{tree}}").strip()
    return rebased_tree == tested_tree


def emit_mode_output(value: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as file:
            file.write(f"mode={value}\n")
    else:
        print(f"mode={value}")
