import re
from pathlib import Path

import pytest

from github_actions_toolkit.verbs import lint_workflows
from github_actions_toolkit.verbs.lint_workflows import (
    ACTIONLINT_BUILDS,
    ZIZMOR_BUILDS,
    found_stage_files,
    found_workflows,
)


def test_audit_binaries_cover_the_same_platforms() -> None:
    assert set(ZIZMOR_BUILDS) == set(ACTIONLINT_BUILDS)


def test_zizmor_builds_carry_sha256_checksums() -> None:
    for tarball_name, checksum in ZIZMOR_BUILDS.values():
        assert tarball_name.startswith("zizmor") and tarball_name.endswith(".tar.gz")
        assert re.fullmatch(r"[0-9a-f]{64}", checksum)


def skip_audit_runners() -> None:
    pass


def lint_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(lint_workflows, "run_actionlint", skip_audit_runners)
    monkeypatch.setattr(lint_workflows, "run_zizmor", skip_audit_runners)
    try:
        lint_workflows.main()
    except SystemExit:
        pass
    return capsys.readouterr().out


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_non_mapping_document_is_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path / ".github" / "workflows" / "flat.yml", "- just\n- a\n- list\n")
    assert "workflow is not a YAML mapping" in lint_report(monkeypatch, tmp_path, capsys)


def test_a_workflow_without_workflow_call_gets_no_reusable_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        tmp_path / ".github" / "workflows" / "woken.yml",
        """
on:
  pull_request:
    branches: [dev]

concurrency:
  group: woken-${{ github.ref }}

jobs:
  woken:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )
    assert lint_report(monkeypatch, tmp_path, capsys) == ""


def test_reusable_workflow_law_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        tmp_path / ".github" / "workflows" / "merge-if-ready.yml",
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
    assert lint_report(monkeypatch, tmp_path, capsys) == ""

    write(
        tmp_path / ".github" / "workflows" / "preflight.yml",
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
    assert "must not declare top-level concurrency" in lint_report(monkeypatch, tmp_path, capsys)

    write(
        tmp_path / ".github" / "workflows" / "hybrid.yml",
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
    assert "workflow_call as its only trigger" in lint_report(monkeypatch, tmp_path, capsys)


def test_stage_files_carry_the_reusable_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        tmp_path / ".github" / "stages" / "build.yml",
        """
on:
  workflow_call:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )
    assert lint_report(monkeypatch, tmp_path, capsys) == ""

    write(
        tmp_path / ".github" / "stages" / "build.yml",
        """
on:
  workflow_call:

concurrency:
  group: build-${{ github.ref }}

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
""",
    )
    assert "must not declare top-level concurrency" in lint_report(monkeypatch, tmp_path, capsys)


def test_found_scan_discovers_workflows_and_stage_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    write(tmp_path / ".github/workflows/one.yml", "jobs: {}")
    write(tmp_path / ".github/workflows/two.yaml", "jobs: {}")
    write(tmp_path / ".github/stages/three.yml", "jobs: {}")
    write(tmp_path / ".github/stages/four.yaml", "jobs: {}")
    assert [path.name for path in found_workflows()] == ["one.yml", "two.yaml"]
    assert [path.name for path in found_stage_files()] == ["four.yaml", "three.yml"]


def test_found_stage_scan_is_empty_without_the_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert found_stage_files() == []
