from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

import typer
import yaml
from bashrun.bash import CalledProcessError, bash, bash_output
from pydantic import TypeAdapter, ValidationError

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

ROOT_DOCUMENT = TypeAdapter(dict[object, object])
STR_MAPPING = TypeAdapter(dict[str, object])

WORKFLOWS_DIRECTORY = Path(".github/workflows")
STAGES_DIRECTORY = Path(".github/stages")
ZIZMOR_CONFIG = Path(__file__).with_name("zizmor.yaml")
ACTIONLINT_VERSION = "1.7.12"
ACTIONLINT_BUILDS = {
    ("Linux", "x86_64"): "linux_amd64",
    ("Linux", "aarch64"): "linux_arm64",
    ("Darwin", "x86_64"): "darwin_amd64",
    ("Darwin", "arm64"): "darwin_arm64",
}
ZIZMOR_VERSION = "1.30.1"
# no upstream checksums file exists, so each build carries its own sha256 — changing the expected hash takes a repo commit
ZIZMOR_BUILDS = {
    ("Linux", "x86_64"): (
        "zizmor-x86_64-unknown-linux-gnu.tar.gz",
        "e65324f4430c2717591937edcec90ccbefaf14c174f8ec9415e03ca875b46e1a",
    ),
    ("Linux", "aarch64"): (
        "zizmor-aarch64-unknown-linux-gnu.tar.gz",
        "7ff1dce33bdd18fd2a4affe63bdd47efcccca97b2cec1c1863ec26e9e2647540",
    ),
    ("Darwin", "x86_64"): (
        "zizmor-x86_64-apple-darwin.tar.gz",
        "10e6b18b11ea07e515a16f0f0518c7b07527bc9977c1fd5698181ce7f3554202",
    ),
    ("Darwin", "arm64"): (
        "zizmor-aarch64-apple-darwin.tar.gz",
        "e28d22b087f9ebb8d99da6e740d348c930f559961c7c3f12badda54f882195a2",
    ),
}
# Bridge actionlint gaps (job.workflow_*, $/ refs, the queue key) until the version pin moves past them
ACTIONLINT_IGNORE_FLAGS = [
    "-ignore",
    r"property.*workflow_repository.*not.defined",
    "-ignore",
    r"property.*workflow_sha.*not.defined",
    "-ignore",
    r"specifying.action.*\\$/.*ref.is.missing",
    "-ignore",
    r"reusable.workflow.call.*\\$/",
    "-ignore",
    r"unexpected.key.*queue.*concurrency.*section",
]


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str


@app.command()
def main() -> None:
    problems: list[Problem] = []
    for lint_file in [*found_workflows(), *found_stage_files()]:
        document: object = yaml.safe_load(lint_file.read_text(encoding="utf-8"))
        root = parse_root_mapping(document)
        if root is None:
            problems.append(file_problem(lint_file, "workflow is not a YAML mapping"))
            continue
        # Fall back to the True key, because yaml 1.1 parses a bare on: key as boolean True
        triggers = parse_str_mapping(root.get("on"))
        if triggers is None:
            triggers = parse_str_mapping(root.get(True))
        if triggers is None or "workflow_call" not in triggers:
            continue
        # A reusable is a callee: the caller owns wake triggers and serialization, so a
        # reusable carrying either puts one file in two roles, and a concurrency group
        # matching the caller's self-deadlocks the call before any job starts.
        if set(triggers) != {"workflow_call"}:
            problems.append(
                file_problem(lint_file, "a reusable workflow must declare workflow_call as its only trigger")
            )
        if parse_str_mapping(root.get("concurrency")) is not None:
            problems.append(
                file_problem(
                    lint_file,
                    "a reusable workflow must not declare top-level concurrency: the caller serializes,"
                    " and a group matching the caller's self-deadlocks the call",
                )
            )
    for problem in problems:
        print(render_problem(problem))
    run_actionlint()
    run_zizmor()
    if problems:
        raise SystemExit(1)


def found_workflows() -> list[Path]:
    if not WORKFLOWS_DIRECTORY.is_dir():
        return []
    return sorted({*WORKFLOWS_DIRECTORY.glob("*.yml"), *WORKFLOWS_DIRECTORY.glob("*.yaml")})


def found_stage_files() -> list[Path]:
    if not STAGES_DIRECTORY.is_dir():
        return []
    return sorted({*STAGES_DIRECTORY.glob("*.yml"), *STAGES_DIRECTORY.glob("*.yaml")})


def run_actionlint() -> None:
    workflow_files = found_workflows()
    if not workflow_files:
        raise SystemExit("no workflow files found in .github/workflows")
    binary = ensure_actionlint()
    command = " ".join([
        f'"{binary}"',
        *ACTIONLINT_IGNORE_FLAGS,
        *[f'"{lint_file}"' for lint_file in [*workflow_files, *found_stage_files()]],
    ])
    try:
        bash(command)
    except CalledProcessError as error:
        raise SystemExit(error.returncode) from error


def run_zizmor() -> None:
    # Audit the repo root offline, passing the stage files explicitly, because the root scan skips .github/stages
    binary = ensure_zizmor()
    command = " ".join([
        f'"{binary}"',
        "--offline",
        "--format",
        "plain",
        "--no-progress",
        "--config",
        f'"{ZIZMOR_CONFIG}"',
        '"."',
        *[f'"{stage_file}"' for stage_file in found_stage_files()],
    ])
    try:
        bash(command)
    except CalledProcessError as error:
        raise SystemExit(error.returncode) from error


def ensure_actionlint() -> Path:
    platform_key = (platform.system(), platform.machine())
    if platform_key not in ACTIONLINT_BUILDS:
        raise SystemExit(f"no actionlint build for {platform.system()}/{platform.machine()}")
    release_base = f"https://github.com/rhysd/actionlint/releases/download/v{ACTIONLINT_VERSION}"
    tarball_name = f"actionlint_{ACTIONLINT_VERSION}_{ACTIONLINT_BUILDS[platform_key]}.tar.gz"
    checksums = bash_output(f"curl -fsSL {release_base}/actionlint_{ACTIONLINT_VERSION}_checksums.txt")
    return ensure_pinned_binary(
        "actionlint",
        ACTIONLINT_VERSION,
        tarball_name,
        expected_checksum(checksums, tarball_name),
        release_base,
    )


def ensure_zizmor() -> Path:
    platform_key = (platform.system(), platform.machine())
    if platform_key not in ZIZMOR_BUILDS:
        raise SystemExit(f"no zizmor build for {platform.system()}/{platform.machine()}")
    tarball_name, expected = ZIZMOR_BUILDS[platform_key]
    release_base = f"https://github.com/zizmorcore/zizmor/releases/download/v{ZIZMOR_VERSION}"
    return ensure_pinned_binary("zizmor", ZIZMOR_VERSION, tarball_name, expected, release_base)


def ensure_pinned_binary(name: str, version: str, tarball_name: str, expected: str, release_base: str) -> Path:
    cache_directory = Path.home() / ".cache" / "github-actions-toolkit" / f"{name}-v{version}"
    binary = cache_directory / name
    if binary.is_file():
        return binary
    cache_directory.mkdir(parents=True, exist_ok=True)
    tarball = cache_directory / tarball_name
    bash(f'curl -fsSL {release_base}/{tarball_name} -o "{tarball}"')
    actual = bash_output(f'sha256sum "{tarball}"').split(maxsplit=1)[0]
    if actual != expected:
        raise SystemExit(f"{name} {version} checksum mismatch for {tarball_name}: expected {expected}, got {actual}")
    bash(f'tar -xzf "{tarball}" -C "{cache_directory}"')
    tarball.unlink()
    if not binary.is_file():
        raise SystemExit(f"{name} binary missing after extracting {tarball_name}")
    return binary


def expected_checksum(checksums: str, tarball_name: str) -> str:
    for line in checksums.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == tarball_name:
            return fields[0]
    raise SystemExit(f"actionlint checksums file has no entry for {tarball_name}")


def parse_root_mapping(value: object) -> dict[object, object] | None:
    try:
        return ROOT_DOCUMENT.validate_python(value)
    except ValidationError:
        return None


def parse_str_mapping(value: object) -> dict[str, object] | None:
    try:
        return STR_MAPPING.validate_python(value)
    except ValidationError:
        return None


def file_problem(path: Path, message: str) -> Problem:
    return Problem(path=path, message=message)


def render_problem(problem: Problem) -> str:
    return f"{problem.path}: {problem.message}"
