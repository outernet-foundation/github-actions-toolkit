from __future__ import annotations

import functools
import json
import re
import textwrap
from dataclasses import dataclass
from importlib.metadata import Distribution
from pathlib import Path
from typing import Annotated

import typer
import yaml
from bashrun.bash import CalledProcessError, bash_output
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError, model_validator

from github_actions_toolkit.config import (
    DEFAULT_CONFIG_PATH,
    JOB_KEY_PATTERN,
    PASSES,
    TOOLKIT_REPOSITORY,
    Channel,
    JobEntry,
    Pass,
    load_config,
)
from github_actions_toolkit.publishing import BUILD_COMMIT_STAMP

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

WORKFLOW_DIRECTORY = Path(".github/workflows")
TEMPLATE_DIRECTORY = Path(__file__).parent.parent / "templates"
STAGE_DIRECTORY = Path(".github/stages")
DOMAIN_WORKFLOW_DIRECTORY = Path(".github/workflows")
SITE_PACKAGES_GLOB = ".venv/lib/python3*/site-packages"
RAW_STAGE_URL = "https://raw.githubusercontent.com/{repository}/{commit}/{path}"
REMOTE_REPOSITORIES = (
    re.compile(r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$"),
    re.compile(r"^https://github\.com/([^/]+/[^/]+?)(?:\.git)?$"),
)
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
# Match up to the first }} outside a quoted string, because braces inside a string literal must stay inside
EXPRESSION_SPAN = re.compile(r"""\$\{\{(?:[^'"}]|'[^']*'|"[^"]*"|}(?!}))*\}\}""")
BARE_INPUT = re.compile(r"^\$\{\{\s*inputs\.([A-Za-z0-9_-]+)\s*\}\}$")
INPUT_REFERENCE = re.compile(r"\binputs\.([A-Za-z0-9_-]+)")
SECRET_REFERENCE = re.compile(r"\bsecrets\.([A-Za-z0-9_-]+)")
NEEDS_REFERENCE = re.compile(r"\bneeds\.([\w-]+)")
RUNS_ON_INPUT = re.compile(r"^\$\{\{\s*fromJSON\(inputs\.runs-on\)\s*\}\}$")
TOOLKIT_TOKEN = re.compile(r"__TOOLKIT__/(?P<path>\S+)")
FAN_MARKER = "# __FAN__"
DEV_FAN_MARKER = "# __DEV_FAN__"
STABLE_FAN_MARKER = "# __STABLE_FAN__"
CONSUMER_SCRIPT_MARKER = "# __IF_CONSUMER_SCRIPT__"
NOT_CONSUMER_SCRIPT_MARKER = "# __IF_NOT_CONSUMER_SCRIPT__"
BLOCK_END_MARKER = "# __END__"
INTEGRATE_SPINE_JOBS = ("gate", "preflight", "release-pr-builds", "merge-if-ready")
RELEASE_SPINE_JOBS = ("prerelease", "release")

type YamlValue = str | bool | int | float | list[YamlValue] | dict[str, YamlValue] | None
type YamlMapping = dict[str, YamlValue]
type StageJobKey = Annotated[str, StringConstraints(pattern=JOB_KEY_PATTERN)]

ROOT_MAPPING: TypeAdapter[dict[str | bool, YamlValue]] = TypeAdapter(dict[str | bool, YamlValue])
STR_MAPPING: TypeAdapter[YamlMapping] = TypeAdapter(YamlMapping)
STRING_LIST = TypeAdapter(list[str])


@dataclass(frozen=True)
class ToolkitRef:
    # Spell none as the $/ self-repository form, because a file cannot hold the sha of the commit that contains it
    sha: str | None

    def spell(self, path: str) -> str:
        return f"$/{path}" if self.sha is None else f"{TOOLKIT_REPOSITORY}/{path}@{self.sha}"


@dataclass(frozen=True)
class TransformContext:
    toolkit: ToolkitRef
    channel: Channel
    # Lead the entry key with the channel where one lane file holds the entry at two channels
    prefix: str
    stage_jobs: frozenset[str]
    resolved_inputs: dict[str, YamlValue]
    bindings: dict[str, str]
    runners: list[str] | None


@dataclass(frozen=True)
class SplicedJob:
    key: str
    # Hold the stage's own needs under the pass prefix, before the spine adds the jobs every fan job waits on
    needs: tuple[str, ...]
    body: YamlMapping


@dataclass(frozen=True)
class SplicedPass:
    jobs: tuple[SplicedJob, ...]
    # Collect the fan jobs no other fan job needs, the ones the job after the fan waits on alone
    tails: tuple[str, ...]


class InputSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default: YamlValue = None


class SecretSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")


class WorkflowCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    secrets: dict[str, SecretSpec] = Field(default_factory=dict)


class StageDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    permissions: YamlMapping | None = None
    env: YamlMapping | None = None
    defaults: YamlMapping | None = None
    workflow_call: WorkflowCall
    jobs: dict[StageJobKey, YamlMapping] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def lift_trigger(cls, data: object) -> object:
        raw = ROOT_MAPPING.validate_python(data)
        # Read the trigger from under the True key when yaml 1.1 read a bare on key as true
        trigger = STR_MAPPING.validate_python(raw["on"] if "on" in raw else raw.get(True))
        if set(trigger) != {"workflow_call"}:
            raise ValueError("a stage declares workflow_call as its only trigger")
        body = {key: value for key, value in raw.items() if key != "on" and key is not True}
        return {**body, "workflow_call": STR_MAPPING.validate_python(trigger["workflow_call"] or {})}


@app.command()
def main(
    check: Annotated[
        bool, typer.Option(help="Verify the committed files match the generated ones, exit non-zero on drift")
    ] = False,
    config: Annotated[Path, typer.Option(help="Publish configuration YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    configuration = load_config(config)
    jobs = configuration.jobs
    if jobs is None:
        print("  publish.yml declares no jobs, so generated workflows are not adopted in this repo")
        return
    consumer_root = config.resolve().parent
    self_mode = self_repository(consumer_root)
    # Pin the generator at the head of the clone the verb runs from, never the consumer checkout
    generator_pin = bash_output("git rev-parse HEAD", cwd=Path(__file__).resolve().parents[3]).strip()
    toolkit = ToolkitRef(sha=None) if self_mode else ToolkitRef(sha=generator_pin)
    stages = {key: acquire_stage(entry, key, consumer_root) for key, entry in jobs.items() if entry.uses is None}
    integrate_pass, dev_pass, stable_pass = PASSES
    integrate = splice_pass(jobs, integrate_pass, stages, toolkit)
    dev = splice_pass(jobs, dev_pass, stages, toolkit)
    stable = splice_pass(jobs, stable_pass, stages, toolkit)
    documents = {
        "integrate.yml": filled_template(
            "integrate.yml",
            toolkit,
            configuration.consumer_script,
            {FAN_MARKER: fan_text(integrate, integrate_pass, mirror_in_heads=True, spine=INTEGRATE_SPINE_JOBS)},
            {
                "__FAN_TAILS__": "".join(f", {tail}" for tail in integrate.tails),
                "__RETRY_WORKFLOW__": "_retry.yml" if self_mode else "retry.yml",
            },
        ),
        "preflight.yml": filled_template("preflight.yml", toolkit, configuration.consumer_script, {}, {}),
        "retry.yml": filled_template("retry.yml", toolkit, configuration.consumer_script, {}, {}),
        "cleanup-pr-releases.yml": filled_template(
            "cleanup-pr-releases.yml", toolkit, configuration.consumer_script, {}, {}
        ),
    }
    if not self_mode:
        documents["release.yml"] = filled_template(
            "release.yml",
            toolkit,
            configuration.consumer_script,
            {
                DEV_FAN_MARKER: fan_text(dev, dev_pass, mirror_in_heads=False, spine=RELEASE_SPINE_JOBS),
                STABLE_FAN_MARKER: fan_text(stable, stable_pass, mirror_in_heads=False, spine=RELEASE_SPINE_JOBS),
            },
            {
                "__DEV_TAILS__": ", ".join(dev.tails),
                "__STABLE_TAILS__": ", ".join(stable.tails),
            },
        )
    prefix = "_" if self_mode else ""
    files = {WORKFLOW_DIRECTORY / f"{prefix}{name}": text for name, text in documents.items()}
    if not check:
        for path, text in files.items():
            destination = consumer_root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8")
            print(f"  wrote {path}")
        return
    drifted = [path for path, text in files.items() if committed(consumer_root / path) != text]
    if drifted:
        spelled = ", ".join(str(path) for path in drifted)
        raise SystemExit(
            f"generated workflows drifted ({spelled}): run"
            " generate-github-workflows and commit the regenerated files with the change"
        )
    print("  generated workflows match the committed files")


def self_repository(consumer_root: Path) -> bool:
    try:
        url = bash_output("git remote get-url origin", cwd=consumer_root).strip()
    except CalledProcessError as error:
        raise SystemExit(f"{consumer_root}: no origin remote to read the consumer repository from") from error
    for pattern in REMOTE_REPOSITORIES:
        if match := pattern.match(url):
            return match.group(1) == TOOLKIT_REPOSITORY
    return False


def acquire_stage(entry: JobEntry, key: str, consumer_root: Path) -> StageDocument:
    stage_path = entry.file
    if stage_path is None and entry.package is not None:
        stage_path = DOMAIN_WORKFLOW_DIRECTORY / f"{key}.yml"
    if stage_path is None:
        stage_path = STAGE_DIRECTORY / f"{key}.yml"
    if entry.path:
        local_path = consumer_root / stage_path
        try:
            text = local_path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise SystemExit(f"{stage_path}: stage file not found in the consumer repository") from error
        return parse_stage_document(text, str(stage_path))
    if entry.package is not None and entry.repository is not None:
        text = fetch_domain_stage(entry.package, entry.repository, stage_path, consumer_root)
        return parse_stage_document(text, f"{entry.repository}/{stage_path.as_posix()}")
    raise SystemExit(f"job '{key}': a uses entry has no stage to acquire")


def parse_stage_document(text: str, origin: str) -> StageDocument:
    try:
        return StageDocument.model_validate(yaml.safe_load(text))
    except ValidationError as error:
        described = ", ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
        )
        raise SystemExit(f"{origin}: {described}") from error
    except yaml.YAMLError as error:
        raise SystemExit(f"{origin}: {error}") from error


def fetch_domain_stage(package: str, repository: str, stage_path: Path, consumer_root: Path) -> str:
    # Read the stamp as a data file through the installed wheel's record, because importing it would run domain code
    candidates = sorted(consumer_root.glob(SITE_PACKAGES_GLOB))
    if len(candidates) != 1:
        venv = consumer_root / ".venv"
        raise SystemExit(f"{venv}: expected exactly one python site-packages, run uv sync before generating")
    distributions = list(Distribution.discover(path=[str(candidates[0])], name=package))
    if not distributions:
        raise SystemExit(f"{package}: not installed in the consumer venv, run uv sync before generating")
    recorded = distributions[0].files
    stamp = next((file for file in recorded or () if file.name == BUILD_COMMIT_STAMP), None)
    if stamp is None:
        raise SystemExit(
            f"{package}: the installed wheel carries no commit stamp: it predates stamping, was published outside"
            " the machinery, or is an editable install"
        )
    commit = Path(stamp.locate()).read_text(encoding="utf-8").strip()
    if not COMMIT_SHA.fullmatch(commit):
        raise SystemExit(f"{package}: the commit stamp {commit!r} is not a full commit sha")
    url = RAW_STAGE_URL.format(repository=repository, commit=commit, path=stage_path.as_posix())
    try:
        return bash_output(f'curl -fsSL "{url}"')
    except CalledProcessError as error:
        raise SystemExit(f"could not fetch the stage {url} (exit {error.returncode})") from error


def splice_pass(
    entries: dict[str, JobEntry], channel_pass: Pass, stages: dict[str, StageDocument], toolkit: ToolkitRef
) -> SplicedPass:
    all_targets = tuple(dict.fromkeys(pass_target.target for pass_target in PASSES))
    jobs: list[SplicedJob] = []
    for key, entry in entries.items():
        if channel_pass.target not in (entry.targets or all_targets):
            continue
        copies = sum(other.workflow == channel_pass.workflow for other in PASSES)
        # Tell the copies apart by channel when one lane file holds the entry at more than one channel
        prefix = f"{channel_pass.channel}-{key}" if copies > 1 else key
        if entry.uses is not None:
            jobs.append(SplicedJob(key=prefix, needs=(), body={"uses": rewrite_toolkit_uses(entry.uses, toolkit)}))
            continue
        stage = stages[key]
        channel = channel_pass.channel
        # Check every channel's map, so a typo fails even where the entry is never spliced
        declared = set(stage.workflow_call.secrets)
        for channel_key, channel_map in entry.secrets.items():
            undeclared = channel_map.keys() - declared
            if undeclared:
                raise SystemExit(
                    f"job '{prefix}': secrets bound under {channel_key} that the stage does not declare:"
                    f" {sorted(undeclared)}"
                )
        bindings = dict(entry.secrets.get(channel, {}))
        runners = entry.runners
        takes_runners = "runs-on" in stage.workflow_call.inputs and any(
            isinstance(runs_on := body.get("runs-on"), str) and RUNS_ON_INPUT.fullmatch(runs_on)
            for body in stage.jobs.values()
        )
        if runners is not None and not takes_runners:
            raise SystemExit(f"job '{prefix}': runners override a stage that takes no runs-on input")
        context = TransformContext(
            toolkit=toolkit,
            channel=channel,
            prefix=prefix,
            stage_jobs=frozenset(stage.jobs),
            resolved_inputs={
                **{
                    name: spec.default
                    for name, spec in stage.workflow_call.inputs.items()
                    if "default" in spec.model_fields_set
                },
                "channel": channel,
            },
            bindings=bindings,
            runners=runners,
        )
        for job_key, job_body in stage.jobs.items():
            composed = {body_key: value for body_key, value in job_body.items() if body_key != "needs"}
            # Let the stage's permissions stand in when the job declares none, as they do inside a reusable workflow
            if stage.permissions is not None and "permissions" not in composed:
                composed["permissions"] = stage.permissions
            for merged_key, stage_level in (("env", stage.env), ("defaults", stage.defaults)):
                if stage_level is not None:
                    job_level = composed.get(merged_key)
                    composed[merged_key] = stage_level if job_level is None else merged(stage_level, job_level)
            needs_value = job_body.get("needs")
            targets = needs_value if isinstance(needs_value, list) else ([] if needs_value is None else [needs_value])
            unknown = [target for target in targets if not (isinstance(target, str) and target in context.stage_jobs)]
            if unknown:
                raise SystemExit(f"job '{context.prefix}': needs names jobs outside the stage: {unknown}")
            needs = tuple(f"{context.prefix}-{target}" for target in targets if isinstance(target, str))
            spliced_body: YamlMapping = {}
            for body_key, value in composed.items():
                if body_key == "runs-on":
                    spliced_body[body_key] = resolved_runs_on(value, context)
                    continue
                spliced_body[body_key] = transform_node(value, context)
            jobs.append(SplicedJob(key=f"{context.prefix}-{job_key}", needs=needs, body=spliced_body))

    needed = {target for job in jobs for target in job.needs}
    return SplicedPass(jobs=tuple(jobs), tails=tuple(job.key for job in jobs if job.key not in needed))


def fan_text(spliced: SplicedPass, channel_pass: Pass, *, mirror_in_heads: bool, spine: tuple[str, ...]) -> str:
    collided = sorted({job.key for job in spliced.jobs} & set(spine))
    if collided:
        raise SystemExit(f"the generated file declares each of these job keys twice: {collided}")
    mirror_present = any(job.key == "mirror" for job in spliced.jobs)
    blocks: list[str] = []
    for job in spliced.jobs:
        body = dict(job.body)
        stage_if = body.pop("if", None)
        takes_mirror = mirror_in_heads and mirror_present and job.key != "mirror"
        needs: list[YamlValue] = [*channel_pass.heads, *(["mirror"] if takes_mirror else []), *job.needs]
        composed: YamlMapping = {}
        if needs:
            composed["needs"] = needs
        # Compose the pass gate with the stage's own if, and the literal kinds are mutually exclusive
        if stage_if is None:
            composed["if"] = "${{ " + channel_pass.gate + " }}"
        if isinstance(stage_if, bool):
            composed["if"] = "${{ " + channel_pass.gate + " && " + ("true" if stage_if else "false") + " }}"
        if isinstance(stage_if, int | float) and not isinstance(stage_if, bool):
            composed["if"] = "${{ " + channel_pass.gate + " && " + str(stage_if) + " }}"
        if (
            isinstance(stage_if, str)
            and stage_if.count("${{") == 1
            and stage_if.startswith("${{")
            and stage_if.endswith("}}")
        ):
            inner = stage_if.removeprefix("${{").removesuffix("}}").strip()
            composed["if"] = "${{ " + channel_pass.gate + " && (" + inner + ") }}"
        if isinstance(stage_if, str) and "${{" not in stage_if and stage_if.strip():
            composed["if"] = "${{ " + channel_pass.gate + " && (" + stage_if.strip() + ") }}"
        if "if" not in composed:
            raise SystemExit("a stage job's if must be one expression, a bare expression, or a literal")
        if job.key == "mirror":
            composed["permissions"] = {"contents": "read", "packages": "write"}
        composed.update(body)
        dumped = yaml.safe_dump({job.key: composed}, sort_keys=False, default_flow_style=False, width=1000000)
        blocks.append(textwrap.indent(dumped.removesuffix("\n"), "  "))
    return "\n\n".join(blocks)


def filled_template(
    name: str,
    toolkit: ToolkitRef,
    consumer_script: bool,
    fan_blocks: dict[str, str],
    plain_tokens: dict[str, str],
) -> str:
    template_lines = (TEMPLATE_DIRECTORY / name).read_text(encoding="utf-8").splitlines()
    body: list[str] = []
    keeping = True
    for line in template_lines:
        stripped = line.strip()
        if stripped == CONSUMER_SCRIPT_MARKER:
            keeping = consumer_script
            continue
        if stripped == NOT_CONSUMER_SCRIPT_MARKER:
            keeping = not consumer_script
            continue
        if stripped == BLOCK_END_MARKER:
            keeping = True
            continue
        if not keeping:
            continue
        if stripped in fan_blocks and not fan_blocks[stripped]:
            continue
        if stripped in fan_blocks:
            body.append(fan_blocks[stripped])
            continue
        filled = TOOLKIT_TOKEN.sub(lambda match: toolkit.spell(match["path"]), line)
        for token, spelled in plain_tokens.items():
            filled = filled.replace(token, spelled)
        # Drop a needs line that filled to empty, because GitHub treats it as the default
        if filled.strip() != "needs: []":
            body.append(filled)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(body)) + "\n"


def transform_node(node: YamlValue, context: TransformContext) -> YamlValue:
    # Transform by node shape, where at most one arm fires
    if isinstance(node, str) and (bare := BARE_INPUT.fullmatch(node)):
        # Pass the value across as itself when the whole string is one bare input reference
        return resolved_value(bare.group(1), context)
    if isinstance(node, str) and node.count("${{") != sum(1 for _ in EXPRESSION_SPAN.finditer(node)):
        raise SystemExit(f"job '{context.prefix}': expression cannot be read: {node}")
    if isinstance(node, str):
        return EXPRESSION_SPAN.sub(functools.partial(rewrite_span, context), node)
    if isinstance(node, list):
        return [transform_node(item, context) for item in node]
    if isinstance(node, dict):
        return {
            item: (
                rewrite_toolkit_uses(value, context.toolkit)
                if item == "uses" and isinstance(value, str)
                else transform_node(value, context)
            )
            for item, value in node.items()
        }
    return node


def resolved_runs_on(value: YamlValue, context: TransformContext) -> YamlValue:
    if not (isinstance(value, str) and RUNS_ON_INPUT.fullmatch(value)):
        return transform_node(value, context)
    if context.runners is not None:
        labels: list[YamlValue] = [*context.runners]
        return labels
    default = context.resolved_inputs.get("runs-on")
    if not isinstance(default, str):
        raise SystemExit(f"job '{context.prefix}': the runs-on input declares no JSON array default")
    try:
        labels = [*STRING_LIST.validate_python(json.loads(default))]
    except (ValidationError, json.JSONDecodeError) as error:
        raise SystemExit(
            f"job '{context.prefix}': the runs-on default {default!r} is not a JSON array of labels"
        ) from error
    return labels


def rewrite_span(context: TransformContext, match: re.Match[str]) -> str:
    body = SECRET_REFERENCE.sub(functools.partial(bound_secret, context), match.group(0))
    body = INPUT_REFERENCE.sub(functools.partial(input_literal, context), body)
    return NEEDS_REFERENCE.sub(functools.partial(spelled_need, context), body)


def bound_secret(context: TransformContext, match: re.Match[str]) -> str:
    slot = match.group(1)
    name = context.bindings.get(slot)
    if name is None:
        raise SystemExit(f"job '{context.prefix}': secret slot '{slot}' has no {context.channel} binding")
    return f"secrets.{name}"


def input_literal(context: TransformContext, match: re.Match[str]) -> str:
    value = resolved_value(match.group(1), context)
    # Spell scalars as literals, because a structured default has no expression spelling
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if value is None:
        return "''"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    raise SystemExit(f"job '{context.prefix}': input '{match.group(1)}' resolves only as a whole expression")


def resolved_value(name: str, context: TransformContext) -> YamlValue:
    if name not in context.resolved_inputs:
        raise SystemExit(f"job '{context.prefix}': input '{name}' is referenced with no declared default")
    return context.resolved_inputs[name]


def spelled_need(context: TransformContext, match: re.Match[str]) -> str:
    name = match.group(1)
    if name not in context.stage_jobs:
        raise SystemExit(f"job '{context.prefix}': needs '{name}' names no job in the stage")
    return f"needs.{context.prefix}-{name}"


def rewrite_toolkit_uses(value: str, toolkit: ToolkitRef) -> str:
    repository_prefix = f"{TOOLKIT_REPOSITORY}/"
    if not value.startswith(repository_prefix):
        return value
    return toolkit.spell(value.removeprefix(repository_prefix).split("@", 1)[0])


def merged(base: YamlValue, override: YamlValue) -> YamlValue:
    # Let a job's own value win over the stage's, key by key
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    return {
        **base,
        **{key: merged(base[key], value) if key in base else value for key, value in override.items()},
    }


def committed(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
