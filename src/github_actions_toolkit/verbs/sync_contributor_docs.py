from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from github_actions_toolkit.verbs.lint_workflows import found_workflows

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

CONTRIBUTING_SOURCE = Path(__file__).parent.parent / "contributor" / "CONTRIBUTING.md"
TEMPLATE_SOURCE = Path(__file__).parent.parent / "contributor" / "PULL_REQUEST_TEMPLATE.md"
DESTINATIONS = (
    (CONTRIBUTING_SOURCE, Path("CONTRIBUTING.md")),
    (TEMPLATE_SOURCE, Path(".github/PULL_REQUEST_TEMPLATE.md")),
)


@app.command()
def main(
    check: Annotated[
        bool, typer.Option(help="Verify the consumer copies match the canonical, exit non-zero on drift")
    ] = False,
) -> None:
    lane_files = {path.name.removeprefix("_") for path in found_workflows()}
    if not {"preflight.yml", "integrate.yml"} <= lane_files:
        print("  no lane pair found, contributor docs are not gated in this repo")
        return
    if not check:
        for source, destination in DESTINATIONS:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            print(f"  wrote {destination} from the canonical")
        return
    absent = [destination for _, destination in DESTINATIONS if not destination.is_file()]
    if absent:
        spelled = ", ".join(str(destination) for destination in absent)
        raise SystemExit(f"expected {spelled} to exist beside the lane files, run sync-contributor-docs")
    drifted = [
        destination
        for source, destination in DESTINATIONS
        if normalized(source.read_bytes()) != normalized(destination.read_bytes())
    ]
    if drifted:
        spelled = ", ".join(str(destination) for destination in drifted)
        raise SystemExit(
            f"contributor docs drifted from the canonical ({spelled}): run"
            " sync-contributor-docs and commit the copies with the pin bump"
        )
    print("  contributor docs match the canonical")


def normalized(content: bytes) -> bytes:
    return content.replace(b"\r\n", b"\n")
