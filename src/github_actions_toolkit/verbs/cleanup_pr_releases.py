from __future__ import annotations

from typing import Annotated

import typer

from github_actions_toolkit.config import Settings
from github_actions_toolkit.releases import delete_releases_by_prefix

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


@app.command()
def main(
    pr_number: Annotated[int, typer.Option(help="PR number whose per-run releases get swept")],
) -> None:
    settings = Settings.model_validate({})
    delete_releases_by_prefix(f"pr-{pr_number}-", settings.github_repository)
