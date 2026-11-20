from __future__ import annotations

import time
from typing import Annotated

import typer
from bashrun.bash import bash, bash_output

from github_actions_toolkit.config import Settings

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

POLL_SECONDS = 5


@app.command()
def main(
    dry_run: Annotated[
        bool, typer.Option(help="Exercise the full machinery and report, with zero side effects")
    ] = False,
) -> None:
    settings = Settings.model_validate({})
    run_id = settings.run_id
    if not run_id:
        raise SystemExit("RUN_ID is not set")
    repository = settings.github_repository

    # Poll the run's status until it completes (the rerun API refuses a live run)
    while True:
        status = bash_output(f"gh api repos/{repository}/actions/runs/{run_id} --jq .status").strip()
        if dry_run:
            print(f"  would re-run run {run_id} once it completes")
            return
        # If the run has completed, stop polling
        if status == "completed":
            break
        time.sleep(POLL_SECONDS)

    # Re-run the completed run
    bash(f"gh api -X POST repos/{repository}/actions/runs/{run_id}/rerun")
    print(f"  re-ran run {run_id}")
