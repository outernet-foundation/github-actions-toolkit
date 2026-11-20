from __future__ import annotations

import platform
import re
from dataclasses import dataclass
from pathlib import Path

import typer
import yaml
from bashrun.bash import CalledProcessError, bash, bash_output
from pydantic import TypeAdapter, ValidationError

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

ROOT_DOCUMENT = TypeAdapter(dict[object, object])
STR_MAPPING = TypeAdapter(dict[str, object])
OBJECT_LIST = TypeAdapter(list[object])

WORKFLOWS_DIRECTORY = Path(".github/workflows")
ACTIONS_DIRECTORY = Path(".github/actions")
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
TOOLKIT_REPOSITORY = "outernet-foundation/github-actions-toolkit"
TOOLKIT_USES = re.compile(rf"^{re.escape(TOOLKIT_REPOSITORY)}/\S+@(\S+)$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
RELEASE_WORKFLOW = Path(".github/workflows/release.yml")
RELEASE_CONCURRENCY = "release-${{ github.ref }}"
INTEGRATE_WORKFLOW = Path(".github/workflows/integrate.yml")
INTEGRATE_CONCURRENCY = "integrate-${{ github.ref }}"
INTEGRATE_WAKE_TYPES = ["opened", "synchronize", "reopened", "labeled", "ready_for_review"]
# consumer refs carry @sha; this repo's own $/ self-call carries no ref — both spell the merge reusable
MERGE_REUSABLE = re.compile(r"/merge-if-ready\.yml(@|$)")
MERGE_CONCURRENCY_GROUP = "merge"
MERGE_CONCURRENCY_QUEUE = "max"
REBASE_REUSABLE = re.compile(r"/rebase\.yml(@|$)")
MODE_OUTPUT = "mode"
RETRY_WORKFLOW = Path(".github/workflows/retry.yml")
# actionlint has not shipped job.workflow_repository/job.workflow_sha support (rhysd/actionlint#696,
# #707); dormant while those contexts live only inside the toolkit-checkout composite (actionlint
# never parses composites) and kept for any future raw spelling in a workflow file. The $/ ignores
# bridge rhysd/actionlint#732: composites and the own preflight call are referenced via $/ and the
# regexes anchor on that spelling so ./-ref and remote-format errors stay live. The queue ignore
# bridges actionlint's concurrency schema predating the queue key (the merge queue spells it).
# All five retire when the ACTIONLINT_VERSION pin moves past the fixes
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


@dataclass(frozen=True)
class JobView:
    uses: str | None
    concurrency: dict[str, object] | None
    needs: list[str]
    if_condition: str | None


@dataclass(frozen=True)
class WorkflowView:
    triggers: dict[str, object] | None
    concurrency: dict[str, object] | None
    jobs: dict[str, JobView]
    uses_values: list[str]


@app.command()
def main() -> None:
    problems: list[Problem] = []
    toolkit_pins: dict[Path, str] = {}
    for workflow_path in found_workflows():
        problems.extend(validate_workflow_file(workflow_path, toolkit_pins))
    for action_path in found_action_files():
        problems.extend(validate_action_file(action_path, toolkit_pins))
    problems.extend(validate_toolkit_pin_consistency(toolkit_pins))
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


def found_action_files() -> list[Path]:
    if not ACTIONS_DIRECTORY.is_dir():
        return []
    return sorted(ACTIONS_DIRECTORY.glob("**/action.yml"))


def validate_workflow_file(path: Path, toolkit_pins: dict[Path, str]) -> list[Problem]:
    document: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    workflow, problems = parse_workflow(path, document)
    if workflow is None:
        return problems
    problems.extend(collect_pin_problems(path, workflow.uses_values, toolkit_pins))
    if workflow.triggers is not None and "workflow_call" in workflow.triggers:
        return problems + validate_reusable_workflow(workflow, path)
    # A repo's own top-level files may carry a leading underscore to stand apart from the reusables
    # beside them — contracts key on the normalized name
    contract_name = path.name.removeprefix("_")
    if contract_name == RELEASE_WORKFLOW.name:
        problems.extend(validate_release_concurrency(workflow, path))
    if contract_name == INTEGRATE_WORKFLOW.name:
        problems.extend(validate_integrate_wake(workflow, path))
        problems.extend(validate_merge_concurrency(workflow, path))
        problems.extend(validate_reuse_gates(workflow, path))
    if contract_name == RETRY_WORKFLOW.name:
        problems.extend(validate_retry_dispatch(workflow, path))
    return problems


# A reusable is a callee: the caller owns wake triggers and serialization, so a
# reusable carrying either puts one file in two roles — and a concurrency group
# matching the caller's cancels the call as a deadlock before any job starts.
def validate_reusable_workflow(workflow: WorkflowView, path: Path) -> list[Problem]:
    problems: list[Problem] = []
    if workflow.triggers is None or set(workflow.triggers) != {"workflow_call"}:
        problems.append(file_problem(path, "a reusable workflow must declare workflow_call as its only trigger"))
    if workflow.concurrency is not None:
        problems.append(
            file_problem(
                path,
                "a reusable workflow must not declare top-level concurrency — the caller serializes,"
                " and a group matching the caller's self-deadlocks the call",
            )
        )
    return problems


def validate_action_file(path: Path, toolkit_pins: dict[Path, str]) -> list[Problem]:
    document: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = parse_root_mapping(document)
    if root is None:
        return [file_problem(path, "action file is not a YAML mapping")]
    runs_value = parse_str_mapping(root.get("runs"))
    entries = parse_object_list(runs_value.get("steps")) if runs_value is not None else None
    uses_values: list[str] = []
    for step in entries or []:
        step_mapping = parse_str_mapping(step)
        if step_mapping is None:
            continue
        step_uses = step_mapping.get("uses")
        if isinstance(step_uses, str):
            uses_values.append(step_uses)
    return collect_pin_problems(path, uses_values, toolkit_pins)


def collect_pin_problems(path: Path, uses_values: list[str], toolkit_pins: dict[Path, str]) -> list[Problem]:
    problems: list[Problem] = []
    for uses in uses_values:
        match = TOOLKIT_USES.fullmatch(uses)
        if match is None:
            continue
        pin = match.group(1)
        if FULL_SHA.fullmatch(pin) is None:
            problems.append(file_problem(path, f"toolkit ref '{uses}' must pin a full 40-hex commit SHA"))
            continue
        toolkit_pins[path] = pin
    return problems


def validate_toolkit_pin_consistency(toolkit_pins: dict[Path, str]) -> list[Problem]:
    distinct = sorted(set(toolkit_pins.values()))
    if len(distinct) > 1:
        spelled = ", ".join(f"{pin} ({path})" for path, pin in toolkit_pins.items())
        return [
            Problem(
                path=Path("."),
                message=f"every toolkit ref in the repo must carry the same SHA, found {spelled}",
            )
        ]
    return []


def validate_release_concurrency(workflow: WorkflowView, path: Path) -> list[Problem]:
    concurrency = workflow.concurrency
    if concurrency is None or concurrency.get("group") != RELEASE_CONCURRENCY:
        return [file_problem(path, f"concurrency group must be {RELEASE_CONCURRENCY} (the per-ref delivery mutex)")]
    if "cancel-in-progress" in concurrency:
        return [
            file_problem(
                path,
                "concurrency must omit cancel-in-progress — a cancelled delivery run loses its"
                " dev-builds section permanently",
            )
        ]
    return []


def validate_integrate_wake(workflow: WorkflowView, path: Path) -> list[Problem]:
    triggers = workflow.triggers
    pull_request = parse_str_mapping(triggers.get("pull_request")) if triggers is not None else None
    problems: list[Problem] = []
    if (
        pull_request is None
        or pull_request.get("types") != INTEGRATE_WAKE_TYPES
        or pull_request.get("branches") != ["dev"]
    ):
        wake_types = ", ".join(INTEGRATE_WAKE_TYPES)
        problems.append(
            file_problem(
                path,
                f"must trigger on pull_request to dev, types [{wake_types}]",
            )
        )
    if triggers is not None and "workflow_run" in triggers:
        problems.append(
            file_problem(path, "workflow_run is forbidden — the PR wakes and the run re-runs are the sole loops")
        )
    concurrency = workflow.concurrency
    if concurrency is None or concurrency.get("group") != INTEGRATE_CONCURRENCY:
        problems.append(
            file_problem(path, f"concurrency group must be {INTEGRATE_CONCURRENCY} (the per-candidate supersession)")
        )
    elif concurrency.get("cancel-in-progress") is not True:
        problems.append(
            file_problem(
                path,
                "concurrency must set cancel-in-progress — a newer wake supersedes the stale attempt",
            )
        )
    return problems


# The rebase-merge API has no non-fast-forward rejection to serialize merges, so the merge-calling
# job holds the global merge queue: one merge window at a time, pending merges wait
def validate_merge_concurrency(workflow: WorkflowView, path: Path) -> list[Problem]:
    problems: list[Problem] = []
    for job_name, job in workflow.jobs.items():
        if job.uses is None or MERGE_REUSABLE.search(job.uses) is None:
            continue
        concurrency = job.concurrency
        if concurrency is None:
            problems.append(
                file_problem(
                    path,
                    f"job '{job_name}' calls the merge-if-ready reusable and must hold the merge queue"
                    f" (concurrency group {MERGE_CONCURRENCY_GROUP} with queue {MERGE_CONCURRENCY_QUEUE})",
                )
            )
            continue
        if concurrency.get("group") != MERGE_CONCURRENCY_GROUP or concurrency.get("queue") != MERGE_CONCURRENCY_QUEUE:
            problems.append(
                file_problem(
                    path,
                    f"job '{job_name}' must declare concurrency group {MERGE_CONCURRENCY_GROUP}"
                    f" with queue {MERGE_CONCURRENCY_QUEUE} — one merge at a time, pending merges wait",
                )
            )
        if concurrency.get("cancel-in-progress") is True:
            problems.append(
                file_problem(
                    path, f"job '{job_name}' must not cancel-in-progress — a cancelled terminal loses the merge"
                )
            )
    return problems


# The mode gates are the label-gated skip spelling: every suite job runs only in full mode,
# and the terminal admits a skipped suite only through the rebase job's reuse proof —
# any other skip path reaching the terminal would be a vacuously green merge
def validate_reuse_gates(workflow: WorkflowView, path: Path) -> list[Problem]:
    rebase_jobs = [
        job_name
        for job_name, job in workflow.jobs.items()
        if job.uses is not None and REBASE_REUSABLE.search(job.uses) is not None
    ]
    if not rebase_jobs:
        return []
    rebase_name = rebase_jobs[0]
    problems: list[Problem] = []
    for job_name, job in workflow.jobs.items():
        if job_name == rebase_name:
            continue
        if job.uses is not None and MERGE_REUSABLE.search(job.uses) is not None:
            problems.extend(validate_merge_gate(job_name, job, rebase_name, path))
            continue
        suite_gate = f"needs.{rebase_name}.outputs.{MODE_OUTPUT} == 'full'"
        if normalize_expression(job.if_condition) != suite_gate:
            problems.append(
                file_problem(
                    path,
                    f"job '{job_name}' must gate on {suite_gate} — only a full-mode run executes the suite",
                )
            )
    return problems


def validate_merge_gate(
    merge_name: str,
    merge_job: JobView,
    rebase_name: str,
    path: Path,
) -> list[Problem]:
    suite_needs = [need for need in merge_job.needs if need != rebase_name]
    if len(suite_needs) != 1 or rebase_name not in merge_job.needs:
        return [
            file_problem(
                path,
                f"job '{merge_name}' must need exactly the rebase job and its one terminal suite"
                " job — the terminal gate reads the rebase output and the suite result",
            )
        ]
    suite_name = suite_needs[0]
    canonical = (
        f"!cancelled() && !failure() && (needs.{suite_name}.result == 'success'"
        f" || needs.{rebase_name}.outputs.{MODE_OUTPUT} == 'reuse')"
    )
    if normalize_expression(merge_job.if_condition) != canonical:
        return [
            file_problem(
                path,
                f"job '{merge_name}' must carry the terminal reuse gate {canonical} — a skipped"
                " suite reaches the merge only through the rebase job's proof",
            )
        ]
    return []


def normalize_expression(condition: str | None) -> str:
    if condition is None:
        return ""
    stripped = condition.strip()
    if stripped.startswith("${{") and stripped.endswith("}}"):
        stripped = stripped[3:-2]
    return " ".join(stripped.split())


def validate_retry_dispatch(workflow: WorkflowView, path: Path) -> list[Problem]:
    triggers = workflow.triggers
    dispatch = parse_str_mapping(triggers.get("workflow_dispatch")) if triggers is not None else None
    inputs = parse_str_mapping(dispatch.get("inputs")) if dispatch is not None else None
    if dispatch is None:
        return [file_problem(path, "must declare workflow_dispatch — the terminal's retry relay entry")]
    if inputs is None:
        return [file_problem(path, "workflow_dispatch must declare the run-id input")]
    entry = parse_str_mapping(inputs.get("run-id"))
    if entry is None or entry.get("type") != "number" or entry.get("required") is not True:
        return [file_problem(path, "workflow_dispatch input run-id must be required with type number")]
    return []


def parse_workflow(path: Path, document: object) -> tuple[WorkflowView | None, list[Problem]]:
    root = parse_root_mapping(document)
    if root is None:
        return None, [file_problem(path, "workflow is not a YAML mapping")]
    jobs_value = parse_str_mapping(root.get("jobs"))
    if jobs_value is None:
        return None, [file_problem(path, "no jobs mapping")]
    problems: list[Problem] = []
    uses_values: list[str] = []
    jobs: dict[str, JobView] = {}
    for job_name, job_value in jobs_value.items():
        job_mapping = parse_str_mapping(job_value)
        if job_mapping is None:
            problems.append(file_problem(path, f"job '{job_name}' is not a mapping"))
            continue
        job_uses = job_mapping.get("uses")
        if isinstance(job_uses, str):
            uses_values.append(job_uses)
        needs_value = job_mapping.get("needs")
        needs: list[str] = []
        if isinstance(needs_value, str):
            needs = [needs_value]
        elif (needs_list := parse_object_list(needs_value)) is not None:
            needs = [str(need) for need in needs_list]
        if_value = job_mapping.get("if")
        jobs[job_name] = JobView(
            uses=job_uses if isinstance(job_uses, str) else None,
            concurrency=parse_str_mapping(job_mapping.get("concurrency")),
            needs=needs,
            if_condition=if_value if isinstance(if_value, str) else None,
        )
        for step in parse_object_list(job_mapping.get("steps")) or []:
            step_mapping = parse_str_mapping(step)
            if step_mapping is None:
                continue
            step_uses = step_mapping.get("uses")
            if isinstance(step_uses, str):
                uses_values.append(step_uses)
    # yaml 1.1 parses a bare `on:` key as boolean True, so the trigger mapping hides under the True key
    triggers = parse_str_mapping(root.get("on"))
    if triggers is None:
        triggers = parse_str_mapping(root.get(True))
    return (
        WorkflowView(
            triggers=triggers,
            concurrency=parse_str_mapping(root.get("concurrency")),
            jobs=jobs,
            uses_values=uses_values,
        ),
        problems,
    )


def run_actionlint() -> None:
    workflow_files = found_workflows()
    if not workflow_files:
        raise SystemExit("no workflow files found in .github/workflows")
    binary = ensure_actionlint()
    command = " ".join([
        f'"{binary}"',
        *ACTIONLINT_IGNORE_FLAGS,
        *[f'"{workflow_file}"' for workflow_file in workflow_files],
    ])
    try:
        bash(command)
    except CalledProcessError as error:
        raise SystemExit(error.returncode) from error


def run_zizmor() -> None:
    # offline is the standing persona: no audit needs GH_TOKEN, so the lint job needs no new credentials
    # repo root, not .github/workflows: the composite actions under .github/actions must be audited too
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


def parse_object_list(value: object) -> list[object] | None:
    try:
        return OBJECT_LIST.validate_python(value)
    except ValidationError:
        return None


def file_problem(path: Path, message: str) -> Problem:
    return Problem(path=path, message=message)


def render_problem(problem: Problem) -> str:
    return f"{problem.path}: {problem.message}"
