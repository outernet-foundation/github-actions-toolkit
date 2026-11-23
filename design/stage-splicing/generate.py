from __future__ import annotations

import dataclasses
import functools
import json
import re
from importlib.metadata import Distribution
from pathlib import Path
from typing import Annotated

import typer
import yaml
from bashrun.bash import bash_output
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

TOOLKIT_REPOSITORY = "outernet-foundation/github-actions-toolkit"
COMMIT_STAMP_NAME = "_toolkit_build_commit"
SPINE_ENTRY_NEEDS = ["gate", "preflight"]
EXPRESSION_SPAN_PATTERN = re.compile(r"\$\{\{[^}]*\}\}")
BARE_INPUT_PATTERN = re.compile(r"\binputs\.(\w+)")
NEEDS_PATTERN = re.compile(r"\bneeds\.([\w-]+)")
SECRETS_PATTERN = re.compile(r"\bsecrets\.([\w-]+)")
# Match both runs-on spellings with and without the fromJSON wrapper
RUNS_ON_PATTERN = re.compile(r"^\$\{\{\s*(?:fromJSON\()?inputs\.runs-on(?:\))?\s*\}\}$")

type YamlValue = str | bool | int | float | None | list[YamlValue] | dict[str, YamlValue]
type YamlMapping = dict[str, YamlValue]

YAML_VALUE_ADAPTER: TypeAdapter[YamlValue] = TypeAdapter(YamlValue)


class PublishConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apps: dict[str, YamlMapping] = Field(default_factory=dict)
    jobs: dict[str, JobEntry] = Field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class TransformContext:
    job: str
    channel: str
    generator_sha: str
    runners: list[str] | None
    resolved: dict[str, YamlValue]
    secrets: dict[str, str]


class StageDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workflow_call: WorkflowCall = Field(default_factory=lambda: WorkflowCall())
    jobs: dict[str, YamlMapping]

    @model_validator(mode="before")
    @classmethod
    def lift_workflow_call(cls, data: YamlValue) -> YamlValue:
        if not isinstance(data, dict):
            return data

        # Read both on spellings because YAML 1.1 parses a bare on as boolean True
        trigger = data.get("on") or data.get(True)
        if not isinstance(trigger, dict):
            return data
        workflow_call = trigger.get("workflow_call")
        lifted = {key: value for key, value in data.items() if key != "on" and key is not True}
        if workflow_call is None:
            return lifted
        return {**lifted, "workflow_call": workflow_call}


class WorkflowCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    secrets: dict[str, SecretSpec] = Field(default_factory=dict)


class InputSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default: YamlValue = None


class SecretSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")


class JobEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str | None = None
    path: Path | None = None
    uses: str | None = None
    repository: str | None = None
    file: str | None = None
    runners: list[str] | None = None
    secrets: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_source(self) -> JobEntry:
        sources = [self.package, self.path, self.uses]
        if sum(source is not None for source in sources) != 1:
            message = "job entry: exactly one of package, path, or uses"
            raise ValueError(message)
        if self.package is not None and self.repository is None:
            message = "job entry: repository is required with package"
            raise ValueError(message)
        return self


def main(
    generator_sha: Annotated[str, typer.Option(envvar="GENERATOR_SHA")],
    check_only: Annotated[bool, typer.Option("--check")] = False,
) -> None:
    if not check_only:
        message = "sketch: spine templates wrap the fan"
        raise NotImplementedError(message)

    # Treat cwd as the consumer root because the verb runs from the toolkit clone
    consumer_root = Path.cwd()
    channel = "pr"
    output_path = Path(".github/workflows/integrate.yml")
    config = PublishConfig.model_validate(yaml.safe_load((consumer_root / "publish.yml").read_text(encoding="utf-8")))

    # Glob the venv's site-packages because a venv holds exactly one python minor version
    candidates = sorted((consumer_root / ".venv" / "lib").glob("python3*/site-packages"))
    if len(candidates) != 1:
        message = f"{consumer_root / '.venv'}: expected exactly one python site-packages, run uv sync before generating"
        raise SystemExit(message)
    site_packages = candidates[0]

    # Resolve each configured package to the commit its installed wheel was minted from
    pins: dict[str, str] = {}
    for package in sorted({entry.package for entry in config.jobs.values() if entry.package is not None}):
        distribution = next(Distribution.discover(path=[str(site_packages)], name=package), None)
        if distribution is None:
            message = f"{package}: not installed in the synced venv, run uv sync before generating"
            raise SystemExit(message)

        # Read the stamp as a data file through the RECORD manifest, never by importing the package
        stamp_file = next((file for file in distribution.files or [] if file.name == COMMIT_STAMP_NAME), None)
        if stamp_file is None:
            message = (
                f"{package}: installed without a commit stamp, "
                "it predates stamping or was published outside the machinery"
            )
            raise SystemExit(message)
        pins[package] = stamp_file.locate().read_text(encoding="utf-8").strip()

    # Fetch each job's stage document from the consumer's tree or the domain repository at the stamped pin
    jobs: dict[str, YamlMapping] = {}
    tails: list[str] = []
    for job_name, entry in config.jobs.items():
        # Treat the arms as exclusive because check_source guarantees exactly one source per entry
        if entry.uses is not None:
            message = f"job {job_name}: foreign uses-entries splice as whole-file calls"
            raise NotImplementedError(message)
        if entry.path is not None:
            stage_document = parse_stage_document(entry.path.read_text(encoding="utf-8"), str(entry.path))
        if entry.package is not None:
            pin = pins[entry.package]
            file_path = entry.file or f".github/workflows/{job_name}.yml"
            url = f"https://raw.githubusercontent.com/{entry.repository}/{pin}/{file_path}"
            stage_document = parse_stage_document(bash_output(f'curl -fsSL "{url}"'), url)

        # Refuse bindings the stage never declared, because a typo in publish.yml must fail at generation
        workflow_call = stage_document.workflow_call
        defaults = {name: spec.default for name, spec in workflow_call.inputs.items()}
        declared_secrets = set(workflow_call.secrets)
        unbound = set(entry.secrets) - declared_secrets
        if unbound:
            message = f"job {job_name}: secrets bound in publish.yml but not declared by the stage document: {sorted(unbound)}"
            raise SystemExit(message)

        # Splice the stage document by resolving its inputs and binding its secret slots
        resolved: dict[str, YamlValue] = {**defaults, "channel": channel}
        context = TransformContext(
            job=job_name,
            channel=channel,
            generator_sha=generator_sha,
            runners=entry.runners,
            resolved=resolved,
            secrets=dict(entry.secrets),
        )
        stage_jobs = transform_node(stage_document.jobs, context)

        # Stamp the mode gate and spine needs on every spliced job because all of them block the merge
        for job_key, job_body in stage_jobs.items():
            prefixed = f"{job_name}-{job_key}"
            job_body["needs"] = list(job_body.get("needs") or SPINE_ENTRY_NEEDS)
            job_body["if"] = "${{ needs.gate.outputs.mode == 'full' }}"
            jobs[prefixed] = job_body
            tails.append(prefixed)

    # Fail on drift between the regenerated expectation and the committed file
    expected = yaml.safe_dump({"jobs": jobs, "job_tails": tails}, sort_keys=False, default_flow_style=False)
    actual = output_path.read_text(encoding="utf-8")
    if expected != actual:
        message = f"{output_path.name}: generated drift, regenerate and commit"
        raise SystemExit(message)


def parse_stage_document(payload: str, origin: str) -> StageDocument:
    try:
        return StageDocument.model_validate(yaml.safe_load(payload))
    except ValidationError as validation_error:
        message = f"{origin}: {validation_error}"
        raise SystemExit(message) from validation_error


def transform_node(node: YamlValue, context: TransformContext) -> YamlValue:
    if isinstance(node, str):
        return EXPRESSION_SPAN_PATTERN.sub(functools.partial(rewrite_span, context), node)
    if isinstance(node, list):
        return [transform_node(item, context) for item in node]
    if not isinstance(node, dict):
        return node

    transformed: dict[str, YamlValue] = {}
    for key, value in node.items():
        if key == "needs":
            targets = value if isinstance(value, list) else [value]
            transformed[key] = [
                f"{context.job}-{target}" if isinstance(target, str) else target for target in targets
            ]
            continue
        if key == "uses" and isinstance(value, str) and value.startswith(f"{TOOLKIT_REPOSITORY}/"):
            transformed[key] = f"{value.split('@', 1)[0]}@{context.generator_sha}"
            continue
        if key == "runs-on" and isinstance(value, str) and RUNS_ON_PATTERN.match(value):
            # Use the consumer runners because they override the domain's declared default
            transformed[key] = context.runners or YAML_VALUE_ADAPTER.validate_python(
                json.loads(str(context.resolved.get("runs-on") or '["ubuntu-latest"]'))
            )
            continue
        transformed[key] = transform_node(value, context)
    return transformed


def rewrite_span(context: TransformContext, span: re.Match[str]) -> str:
    body = span.group(0)
    body = SECRETS_PATTERN.sub(functools.partial(bound_secret_name, context.job, context.secrets), body)
    body = BARE_INPUT_PATTERN.sub(functools.partial(resolved_input_value, context.job, context.resolved), body)
    return NEEDS_PATTERN.sub(lambda match: f"{context.job}-{match.group(1)}", body)


def bound_secret_name(job: str, binding: dict[str, str], match: re.Match[str]) -> str:
    slot = match.group(1)
    bound = binding.get(slot)
    if bound is None:
        message = f"job {job} references secret slot {slot} with no binding in publish.yml"
        raise SystemExit(message)
    return f"secrets.{bound}"


def resolved_input_value(job: str, resolved: dict[str, YamlValue], match: re.Match[str]) -> str:
    name = match.group(1)
    if name not in resolved:
        message = f"job {job} references input {name} with no declared default"
        raise SystemExit(message)
    value = resolved[name]
    if isinstance(value, str):
        return value
    return json.dumps(value)


app = typer.Typer()
app.command()(main)

if __name__ == "__main__":
    app()
