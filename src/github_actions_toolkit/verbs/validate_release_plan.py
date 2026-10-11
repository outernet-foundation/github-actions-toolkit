from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from github_actions_toolkit.config import DEFAULT_CONFIG_PATH, load_config
from github_actions_toolkit.plan import compute_release_plan

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


@app.command()
def main(
    config: Annotated[Path, typer.Option(help="Publish configuration YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    compute_release_plan(load_config(config))
