from __future__ import annotations

from typing import Annotated

import typer
from bashrun.bash import bash_check

from github_actions_toolkit.config import Settings
from github_actions_toolkit.merging import candidate_ref, tested_tag
from github_actions_toolkit.releases import delete_releases_by_prefix

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


@app.command()
def main(
    pr_number: Annotated[int, typer.Option(help="PR number whose per-run releases get swept")],
) -> None:
    settings = Settings.model_validate({})
    delete_releases_by_prefix(f"pr-{pr_number}-", settings.github_repository)

    candidate_branch = candidate_ref(pr_number)
    if bash_check(f"gh api -X DELETE repos/{settings.github_repository}/git/{candidate_branch}"):
        print(f"  deleted {candidate_branch}")

    marker_tag = tested_tag(pr_number)
    if bash_check(f"gh api -X DELETE repos/{settings.github_repository}/git/refs/tags/{marker_tag}"):
        print(f"  deleted refs/tags/{marker_tag}")
