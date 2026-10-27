from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from github_actions_toolkit.config import DEFAULT_CONFIG_PATH, PublishConfig, load_config
from github_actions_toolkit.plan import app_base_version

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

OUTPUT_KEY = "matrix"
LEGS = TypeAdapter(list[dict[str, object]])


@app.command()
def main(
    key: Annotated[
        str, typer.Option(help="Output key the envelope lands under (job output name at the call site)")
    ] = OUTPUT_KEY,
    config: Annotated[Path, typer.Option(help="Publish configuration YAML")] = DEFAULT_CONFIG_PATH,
    allow_empty: Annotated[
        bool,
        typer.Option(
            "--allow-empty", help="Emit an empty envelope for an empty leg list instead of failing (gated fanouts)"
        ),
    ] = False,
) -> None:
    try:
        document = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        raise SystemExit(f"stdin is not valid JSON: {error}") from error
    try:
        legs = LEGS.validate_python(document)
    except ValidationError as error:
        raise SystemExit(f"stdin must be a JSON array of leg objects: {error}") from error
    if not legs and not allow_empty:
        raise SystemExit("empty leg list — refusing to emit an empty matrix envelope")
    # Version stamping is the release plan's only consumer; a repo with no releasable
    # projects (docker legs, empty matrices) carries no publish.yml, so load it only
    # when a project-carrying leg exists.
    project_legs = [leg for leg in legs if "project" in leg]
    if project_legs:
        publish_config = load_config(config)
        owners = owning_apps_by_project(publish_config)
        base_versions: dict[str, str] = {}
        for leg in project_legs:
            project = leg["project"]
            if not isinstance(project, str):
                raise SystemExit(f"leg 'project' must be a string, got '{project}'")
            application = owners.get(project)
            if application is None:
                continue
            if application not in base_versions:
                base_versions[application] = app_base_version(publish_config.apps[application], application)
            leg["version"] = base_versions[application]
    envelope = json.dumps({"include": legs}, separators=(",", ":"))
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as file:
            file.write(f"{key}={envelope}\n")
    else:
        print(f"{key}={envelope}")


def owning_apps_by_project(publish_config: PublishConfig) -> dict[str, str]:
    owners: dict[str, str] = {}
    for application, app_config in publish_config.apps.items():
        for build in app_config.builds:
            existing = owners.get(build.project)
            if existing is not None and existing != application:
                raise SystemExit(f"project '{build.project}' is built by apps '{existing}' and '{application}'")
            owners[build.project] = application
    return owners
