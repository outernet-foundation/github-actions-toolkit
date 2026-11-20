from __future__ import annotations

from subprocess import CalledProcessError
from typing import Annotated

import typer
from bashrun.bash import bash, bash_output

from github_actions_toolkit.config import Settings
from github_actions_toolkit.refs import (
    BASE_BRANCH,
    FETCH_DEV_COMMAND,
    GIT_COMMAND,
    pull_request_number_from_ref,
    candidate_ref,
)

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


@app.command()
def main(
    dry_run: Annotated[
        bool, typer.Option(help="Exercise the full machinery and report, with zero side effects")
    ] = False,
) -> None:
    settings = Settings.model_validate({})
    pr_number = pull_request_number_from_ref(settings.github_ref)

    bash(FETCH_DEV_COMMAND)
    if dry_run:
        print(f"  would rebuild PR #{pr_number} onto the {BASE_BRANCH} tip and force-push {candidate_ref(pr_number)}")
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
        ) from None

    # Force-push the rebased head as the candidate ref the rest of the run tests
    candidate_branch = candidate_ref(pr_number)
    bash(f"{GIT_COMMAND} push origin +HEAD:{candidate_branch}")
    print(f"  force-pushed {candidate_branch}")
