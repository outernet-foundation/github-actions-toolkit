from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings
from strictyaml import load as load_strict_yaml

DEFAULT_CONFIG_PATH = Path("publish.yml")
BOATYARD_CONFIG_PATH = Path("boatyard.yml")
KNOWN_REGISTRIES = frozenset({"nuget", "npm", "pypi"})
DEVKIT_DOCUMENT = TypeAdapter(dict[object, object])
TOOLKIT_REPOSITORY = "outernet-foundation/github-actions-toolkit"
TOOLKIT_MIRROR_WORKFLOW = f"{TOOLKIT_REPOSITORY}/.github/workflows/mirror.yml"
JOB_KEY_PATTERN = r"^[A-Za-z_][A-Za-z0-9_-]*$"
DISTRIBUTION_NAME_PATTERN = r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$"
REPOSITORY_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
PINNED_USES_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[^@\s]+@[0-9a-f]{40}$"
SLOT_NAME_PATTERN = r"^[A-Za-z0-9_-]+$"
BINDING_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
ENV_NAME_PATTERN = r"^[A-Z][A-Z0-9_]*$"

type Channel = Literal["pr", "dev", "stable"]
type Target = Literal["integrate", "release-dev", "release-stable"]
type JobKey = Annotated[str, StringConstraints(pattern=JOB_KEY_PATTERN)]
type SecretSlot = Annotated[str, StringConstraints(pattern=SLOT_NAME_PATTERN)]
type SecretName = Annotated[str, StringConstraints(pattern=BINDING_NAME_PATTERN)]
type SecretBindings = dict[SecretSlot, SecretName]
type EnvName = Annotated[str, StringConstraints(pattern=ENV_NAME_PATTERN)]
type EnvBindings = dict[EnvName, SecretName]


@dataclass(frozen=True)
class Pass:
    target: Target
    channel: Channel
    # Leave none under integrate, where the gate job selects the run
    branch: str | None
    # Name the lane file the pass lands in, which both release passes share
    workflow: str
    # Carry this condition on every spliced job in the pass
    gate: str
    # Make every spliced job need these spine jobs
    heads: tuple[str, ...]


PASSES = (
    Pass(
        target="integrate",
        channel="pr",
        branch=None,
        workflow="integrate.yml",
        gate="needs.gate.outputs.mode == 'full'",
        heads=("gate", "preflight"),
    ),
    Pass(
        target="release-dev",
        channel="dev",
        branch="dev",
        workflow="release.yml",
        gate="github.ref == 'refs/heads/dev'",
        heads=(),
    ),
    Pass(
        target="release-stable",
        channel="stable",
        branch="main",
        workflow="release.yml",
        gate="github.ref == 'refs/heads/main'",
        heads=(),
    ),
)


class Settings(BaseSettings):
    github_token: str = ""
    nuget_api_key: str = ""
    github_repository: str = ""
    github_actor: str = ""
    github_workspace: str = ""
    github_ref: str = ""
    github_sha: str = ""
    github_path: str | None = None
    github_server_url: str = ""
    github_run_id: str = ""
    github_run_attempt: str = ""
    run_id: str = ""
    pr_head_sha: str = ""
    pr_event_action: str = ""
    retry_workflow: str = "retry.yml"

    @model_validator(mode="after")
    def require_runner_environment(self) -> Self:
        missing = [
            env_var
            for env_var, value in (
                ("GITHUB_REPOSITORY", self.github_repository),
                ("GITHUB_ACTOR", self.github_actor),
                ("GITHUB_WORKSPACE", self.github_workspace),
            )
            if not value
        ]
        if missing:
            raise SystemExit(f"{', '.join(missing)} not set — these verbs read the GitHub runner environment")
        return self


class PackageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path
    major_minor: str = Field(pattern=r"^\d+\.\d+$")
    registry: str
    identity: str


class BuildArtifactConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str
    platform: str
    file: str


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path
    major_minor: str = Field(pattern=r"^\d+\.\d+$")
    builds: list[BuildArtifactConfig] = Field(min_length=1)


class JobEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str | None = Field(default=None, pattern=DISTRIBUTION_NAME_PATTERN)
    # Set true to select a stage file inside the consumer repository
    path: bool | None = None
    uses: str | None = Field(default=None, pattern=PINNED_USES_PATTERN)
    repository: str | None = Field(default=None, pattern=REPOSITORY_PATTERN)
    file: Path | None = None
    runners: list[str] | None = Field(default=None, min_length=1)
    secrets: dict[Channel, SecretBindings] = Field(default_factory=dict)
    env: dict[Channel, EnvBindings] = Field(default_factory=dict)
    targets: list[Target] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def check_source(self) -> Self:
        sources = [self.package is not None, self.path is True, self.uses is not None]
        if sum(sources) != 1:
            raise ValueError("job entry: exactly one of package, path, or uses")
        if self.package is not None and self.repository is None:
            raise ValueError("job entry: repository is required with package")
        if self.package is None and self.repository is not None:
            raise ValueError("job entry: repository is read only with package")
        if self.uses is not None and (self.file is not None or self.runners is not None or self.secrets or self.env):
            raise ValueError("job entry: a uses entry takes no file, runners, secrets, or env")
        reserved = sorted(
            name for bindings in self.env.values() for name in bindings if name.startswith(("GITHUB_", "RUNNER_"))
        )
        if reserved:
            raise ValueError(f"job entry: env bindings must not use runner-reserved names: {reserved}")
        if self.file is not None and (self.file.is_absolute() or ".." in self.file.parts):
            raise ValueError("job entry: file is a path inside the consumer repository")
        if self.targets is not None and len(set(self.targets)) != len(self.targets):
            raise ValueError("job entry: targets lists each target once")
        return self


class PublishConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packages: dict[str, PackageConfig] = Field(default_factory=dict)
    apps: dict[str, AppConfig] = Field(default_factory=dict)
    jobs: dict[JobKey, JobEntry] | None = None
    consumer_script: bool = Field(default=True, alias="consumer-script")

    @field_validator("jobs", mode="before")
    @classmethod
    def accept_the_bare_key(cls, value: object) -> object:
        # Accept the bare key's empty string as the empty map, because strictyaml forbids flow mappings
        if value == "":
            return {}
        return value

    @model_validator(mode="after")
    def validate_registry_names(self) -> Self:
        for name, package in self.packages.items():
            if package.registry not in KNOWN_REGISTRIES:
                raise ValueError(f"package '{name}' declares unknown registry '{package.registry}'")
        return self

    @model_validator(mode="after")
    def validate_mirror_slot(self) -> Self:
        if self.jobs is None:
            return self
        mirror = self.jobs.get("mirror")
        if mirror is not None and (mirror.uses is None or not mirror.uses.startswith(f"{TOOLKIT_MIRROR_WORKFLOW}@")):
            raise ValueError("job 'mirror' calls the toolkit's mirror.yml, which is the generator's mirror slot")
        return self


def load_config(path: Path) -> PublishConfig:
    data = load_strict_yaml(path.read_text(encoding="utf-8")).data
    return PublishConfig.model_validate(data if data else {})


def built_images() -> bool:
    # A presence probe over boatyard's root config, not schema consumption —
    # importing boatyard here is a resolver cycle.
    if not BOATYARD_CONFIG_PATH.is_file():
        return False
    document: object = yaml.safe_load(BOATYARD_CONFIG_PATH.read_text(encoding="utf-8"))
    try:
        declarations = DEVKIT_DOCUMENT.validate_python(document)
    except ValidationError:
        return False
    repository = declarations.get("repository")
    return isinstance(repository, str) and repository != ""
