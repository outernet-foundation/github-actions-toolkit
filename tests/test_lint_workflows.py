import re
from pathlib import Path

import pytest

from github_actions_toolkit.verbs.lint_workflows import (
    ACTIONLINT_BUILDS,
    INTEGRATE_WORKFLOW,
    RETRY_WORKFLOW,
    Problem,
    RELEASE_WORKFLOW,
    ZIZMOR_BUILDS,
    found_action_files,
    found_workflows,
    render_problem,
    validate_action_file,
    validate_toolkit_pin_consistency,
    validate_workflow_file,
)

GOOD_SHA = "a" * 40
OTHER_SHA = "b" * 40
TOOLKIT = "outernet-foundation/github-actions-toolkit"


def test_audit_binaries_cover_the_same_platforms() -> None:
    assert set(ZIZMOR_BUILDS) == set(ACTIONLINT_BUILDS)


def test_zizmor_builds_carry_sha256_checksums() -> None:
    for tarball_name, checksum in ZIZMOR_BUILDS.values():
        assert tarball_name.startswith("zizmor-") and tarball_name.endswith(".tar.gz")
        assert re.fullmatch(r"[0-9a-f]{64}", checksum)


def messages_of(problems: list[Problem]) -> list[str]:
    return [render_problem(problem) for problem in problems]


def rendered(problems: list[Problem]) -> str:
    return " ".join(messages_of(problems))


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def workflow_with_uses(uses: str) -> str:
    return f"""
jobs:
  job:
    runs-on: ubuntu-latest
    steps:
      - uses: {uses}
"""


def test_toolkit_ref_with_full_sha_is_accepted(tmp_path: Path) -> None:
    path = write(tmp_path / "workflow.yml", workflow_with_uses(f"{TOOLKIT}/.github/workflows/preflight.yml@{GOOD_SHA}"))
    pins: dict[Path, str] = {}
    assert messages_of(validate_workflow_file(path, pins)) == []
    assert pins == {path: GOOD_SHA}


def test_toolkit_ref_without_full_sha_is_flagged(tmp_path: Path) -> None:
    path = write(tmp_path / "workflow.yml", workflow_with_uses(f"{TOOLKIT}/.github/workflows/preflight.yml@dev"))
    pins: dict[Path, str] = {}
    assert "must pin a full 40-hex commit SHA" in rendered(validate_workflow_file(path, pins))


def test_short_sha_is_flagged(tmp_path: Path) -> None:
    path = write(
        tmp_path / "workflow.yml", workflow_with_uses(f"{TOOLKIT}/.github/workflows/preflight.yml@{GOOD_SHA[:12]}")
    )
    pins: dict[Path, str] = {}
    assert "must pin a full 40-hex commit SHA" in rendered(validate_workflow_file(path, pins))


def test_non_toolkit_refs_are_not_pin_checked(tmp_path: Path) -> None:
    path = write(tmp_path / "workflow.yml", workflow_with_uses("actions/checkout@v5"))
    pins: dict[Path, str] = {}
    assert messages_of(validate_workflow_file(path, pins)) == []


def test_divergent_toolkit_pins_across_files_are_flagged(tmp_path: Path) -> None:
    first = write(tmp_path / "one.yml", workflow_with_uses(f"{TOOLKIT}/.github/workflows/preflight.yml@{GOOD_SHA}"))
    second = write(tmp_path / "two.yml", workflow_with_uses(f"{TOOLKIT}/.github/workflows/mirror.yml@{OTHER_SHA}"))
    pins: dict[Path, str] = {}
    validate_workflow_file(first, pins)
    validate_workflow_file(second, pins)
    assert "must carry the same SHA" in rendered(validate_toolkit_pin_consistency(pins))


def test_agreeing_toolkit_pins_pass(tmp_path: Path) -> None:
    first = write(tmp_path / "one.yml", workflow_with_uses(f"{TOOLKIT}/.github/workflows/preflight.yml@{GOOD_SHA}"))
    second = write(tmp_path / "two.yml", workflow_with_uses(f"{TOOLKIT}/.github/workflows/mirror.yml@{GOOD_SHA}"))
    pins: dict[Path, str] = {}
    validate_workflow_file(first, pins)
    validate_workflow_file(second, pins)
    assert messages_of(validate_toolkit_pin_consistency(pins)) == []


def test_yaml_anchors_on_the_uses_scalar_resolve(tmp_path: Path) -> None:
    text = f"""
jobs:
  one:
    runs-on: ubuntu-latest
    steps:
      - uses: &toolkit {TOOLKIT}/.github/workflows/preflight.yml@{GOOD_SHA}
  two:
    runs-on: ubuntu-latest
    steps:
      - uses: *toolkit
"""
    path = write(tmp_path / "workflow.yml", text)
    pins: dict[Path, str] = {}
    assert messages_of(validate_workflow_file(path, pins)) == []
    assert pins == {path: GOOD_SHA}


def test_job_level_uses_refs_are_pin_checked(tmp_path: Path) -> None:
    text = f"""
jobs:
  preflight:
    uses: {TOOLKIT}/.github/workflows/preflight.yml@dev
"""
    path = write(tmp_path / "workflow.yml", text)
    pins: dict[Path, str] = {}
    assert "must pin a full 40-hex commit SHA" in rendered(validate_workflow_file(path, pins))


VALID_RELEASE = """
concurrency:
  group: release-${{ github.ref }}

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""


def test_release_concurrency_shape_is_enforced(tmp_path: Path) -> None:
    valid = write(tmp_path / RELEASE_WORKFLOW, VALID_RELEASE)
    assert messages_of(validate_workflow_file(valid, {})) == []

    canceling = VALID_RELEASE.replace(
        "group: release-${{ github.ref }}", "group: release-${{ github.ref }}\n  cancel-in-progress: true"
    )
    cancel = write(tmp_path / RELEASE_WORKFLOW, canceling)
    assert "must omit cancel-in-progress" in rendered(validate_workflow_file(cancel, {}))

    wrong = write(tmp_path / RELEASE_WORKFLOW, VALID_RELEASE.replace("release-${{ github.ref }}", "other"))
    assert "concurrency group must be release-${{ github.ref }}" in rendered(validate_workflow_file(wrong, {}))


def test_release_contract_does_not_apply_to_other_filenames(tmp_path: Path) -> None:
    path = write(tmp_path / "nightly.yml", VALID_RELEASE.replace("release-${{ github.ref }}", "nightly"))
    assert messages_of(validate_workflow_file(path, {})) == []


VALID_INTEGRATE = f"""
on:
  pull_request:
    branches: [dev]
    types: [opened, synchronize, reopened, labeled]

concurrency:
  group: integrate-${{{{ github.ref }}}}
  cancel-in-progress: true

jobs:
  preflight:
    uses: ./.github/workflows/preflight.yml
  merge-if-ready:
    needs: preflight
    concurrency:
      group: merge
      queue: max
    uses: {TOOLKIT}/.github/workflows/merge-if-ready.yml@{GOOD_SHA}
"""


def test_integrate_wake_contract_is_enforced(tmp_path: Path) -> None:
    valid = write(tmp_path / INTEGRATE_WORKFLOW, VALID_INTEGRATE)
    assert messages_of(validate_workflow_file(valid, {})) == []

    bad_types = VALID_INTEGRATE.replace(
        "types: [opened, synchronize, reopened, labeled]", "types: [labeled, synchronize]"
    )
    typed = write(tmp_path / INTEGRATE_WORKFLOW, bad_types)
    assert "types [opened, synchronize, reopened, labeled]" in rendered(validate_workflow_file(typed, {}))

    workflow_run = VALID_INTEGRATE.replace(
        "\nconcurrency:\n  group: integrate-${{ github.ref }}",
        "\n  workflow_run:\n    workflows: [Integrate]\n\nconcurrency:\n  group: integrate-${{ github.ref }}",
    )
    runner = write(tmp_path / INTEGRATE_WORKFLOW, workflow_run)
    assert "workflow_run is forbidden" in rendered(validate_workflow_file(runner, {}))

    wrong_group = write(tmp_path / INTEGRATE_WORKFLOW, VALID_INTEGRATE.replace("integrate-", "other-"))
    assert "concurrency group must be integrate-${{ github.ref }}" in rendered(validate_workflow_file(wrong_group, {}))

    patient = write(tmp_path / INTEGRATE_WORKFLOW, VALID_INTEGRATE.replace("  cancel-in-progress: true\n", ""))
    assert "must set cancel-in-progress" in rendered(validate_workflow_file(patient, {}))


VALID_RETRY = """
on:
  workflow_dispatch:
    inputs:
      run-id:
        type: number
        required: true

jobs:
  retry:
    uses: ./.github/workflows/retry.yml
"""


def test_retry_dispatch_contract_is_enforced(tmp_path: Path) -> None:
    valid = write(tmp_path / RETRY_WORKFLOW, VALID_RETRY)
    assert messages_of(validate_workflow_file(valid, {})) == []

    missing_dispatch = write(tmp_path / RETRY_WORKFLOW, VALID_RETRY.replace("  workflow_dispatch:\n", "  push:\n"))
    assert "must declare workflow_dispatch" in rendered(validate_workflow_file(missing_dispatch, {}))

    no_inputs = write(
        tmp_path / RETRY_WORKFLOW,
        VALID_RETRY.replace("      run-id:\n        type: number\n        required: true\n", ""),
    )
    assert "must declare the run-id input" in rendered(validate_workflow_file(no_inputs, {}))

    wrong_type = write(tmp_path / RETRY_WORKFLOW, VALID_RETRY.replace("type: number", "type: string"))
    assert "run-id must be required with type number" in rendered(validate_workflow_file(wrong_type, {}))

    optional = write(tmp_path / RETRY_WORKFLOW, VALID_RETRY.replace("        required: true\n", ""))
    assert "run-id must be required with type number" in rendered(validate_workflow_file(optional, {}))


def test_integrate_contract_does_not_apply_to_other_filenames(tmp_path: Path) -> None:
    narrowed = VALID_INTEGRATE.replace("types: [opened, synchronize, reopened, labeled]", "types: [synchronize]")
    path = write(tmp_path / "continuous.yml", narrowed)
    assert messages_of(validate_workflow_file(path, {})) == []


def test_merge_queue_contract_is_enforced(tmp_path: Path) -> None:
    valid = write(tmp_path / INTEGRATE_WORKFLOW, VALID_INTEGRATE)
    assert messages_of(validate_workflow_file(valid, {})) == []

    unqueued = write(
        tmp_path / INTEGRATE_WORKFLOW,
        VALID_INTEGRATE.replace("    concurrency:\n      group: merge\n      queue: max\n", ""),
    )
    assert "must hold the merge queue" in rendered(validate_workflow_file(unqueued, {}))

    wrong_group = write(tmp_path / INTEGRATE_WORKFLOW, VALID_INTEGRATE.replace("group: merge", "group: other"))
    assert "must declare concurrency group merge with queue max" in rendered(validate_workflow_file(wrong_group, {}))

    canceling_pending = write(
        tmp_path / INTEGRATE_WORKFLOW,
        VALID_INTEGRATE.replace("\n      queue: max", ""),
    )
    assert "must declare concurrency group merge with queue max" in rendered(
        validate_workflow_file(canceling_pending, {})
    )

    canceling = write(
        tmp_path / INTEGRATE_WORKFLOW,
        VALID_INTEGRATE.replace("      queue: max\n", "      queue: max\n      cancel-in-progress: true\n"),
    )
    assert "must not cancel-in-progress" in rendered(validate_workflow_file(canceling, {}))


def test_merge_queue_contract_ignores_a_merge_job_that_is_not_called(tmp_path: Path) -> None:
    without_merge = VALID_INTEGRATE.replace(
        "  merge-if-ready:\n"
        "    needs: preflight\n"
        "    concurrency:\n"
        "      group: merge\n"
        "      queue: max\n"
        f"    uses: {TOOLKIT}/.github/workflows/merge-if-ready.yml@{GOOD_SHA}\n",
        "",
    )
    path = write(tmp_path / INTEGRATE_WORKFLOW, without_merge)
    assert messages_of(validate_workflow_file(path, {})) == []


def test_underscore_prefixed_files_validate_under_their_contracts(tmp_path: Path) -> None:
    valid = write(tmp_path / f"_{INTEGRATE_WORKFLOW.name}", VALID_INTEGRATE)
    assert messages_of(validate_workflow_file(valid, {})) == []

    bad_types = VALID_INTEGRATE.replace(
        "types: [opened, synchronize, reopened, labeled]", "types: [labeled, synchronize]"
    )
    typed = write(tmp_path / f"_{INTEGRATE_WORKFLOW.name}", bad_types)
    assert "types [opened, synchronize, reopened, labeled]" in rendered(validate_workflow_file(typed, {}))

    retry = write(tmp_path / f"_{RETRY_WORKFLOW.name}", VALID_RETRY)
    assert messages_of(validate_workflow_file(retry, {})) == []

    no_dispatch = write(
        tmp_path / f"_{RETRY_WORKFLOW.name}", VALID_RETRY.replace("  workflow_dispatch:\n", "  push:\n")
    )
    assert "must declare workflow_dispatch" in rendered(validate_workflow_file(no_dispatch, {}))


def test_reusable_workflow_law_is_enforced(tmp_path: Path) -> None:
    pure = write(
        tmp_path / "merge-if-ready.yml",
        """
on:
  workflow_call:
    secrets:
      merge-bot-private-key:
        required: true

jobs:
  merge-if-ready:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )
    assert messages_of(validate_workflow_file(pure, {})) == []

    serializing = write(
        tmp_path / "preflight.yml",
        """
on:
  workflow_call:

concurrency:
  group: preflight-${{ github.ref }}

jobs:
  preflight:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )
    assert "must not declare top-level concurrency" in rendered(validate_workflow_file(serializing, {}))

    hybrid = write(
        tmp_path / "hybrid.yml",
        """
on:
  pull_request:
    branches: [dev]
    types: [labeled]
  workflow_call:

jobs:
  hybrid:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )
    assert "workflow_call as its only trigger" in rendered(validate_workflow_file(hybrid, {}))


def test_action_files_are_scanned_for_toolkit_pins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    write(
        tmp_path / ".github/actions/release/action.yml",
        f"""
runs:
  using: composite
  steps:
    - uses: {TOOLKIT}/.github/actions/release@{GOOD_SHA}
""",
    )
    assert [path.name for path in found_action_files()] == ["action.yml"]
    pins: dict[Path, str] = {}
    problems = validate_action_file(found_action_files()[0], pins)
    assert messages_of(problems) == []
    assert pins == {Path(".github/actions/release/action.yml"): GOOD_SHA}


def test_found_scan_discovers_yml_and_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    write(tmp_path / ".github/workflows/one.yml", "jobs: {}")
    write(tmp_path / ".github/workflows/two.yaml", "jobs: {}")
    assert [path.name for path in found_workflows()] == ["one.yml", "two.yaml"]
