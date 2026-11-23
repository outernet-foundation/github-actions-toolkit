from __future__ import annotations

from pathlib import Path

import pytest

from github_actions_toolkit.verbs import sync_contributor_docs


def lane_tree(tmp_path: Path) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "workflows" / "integrate.yml").write_text("on: {}\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows" / "preflight.yml").write_text("on: {}\n", encoding="utf-8")


def test_check_passes_after_a_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    lane_tree(tmp_path)
    sync_contributor_docs.main(check=False)
    sync_contributor_docs.main(check=True)


def test_check_fails_on_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    lane_tree(tmp_path)
    sync_contributor_docs.main(check=False)
    (tmp_path / "CONTRIBUTING.md").write_text("local edits\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_request:
        sync_contributor_docs.main(check=True)
    assert "drifted" in str(exit_request.value)


def test_check_fails_when_a_copy_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    lane_tree(tmp_path)
    with pytest.raises(SystemExit) as exit_request:
        sync_contributor_docs.main(check=True)
    assert "expected" in str(exit_request.value)


def test_check_fails_on_newline_only_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    lane_tree(tmp_path)
    sync_contributor_docs.main(check=False)
    content = (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").read_bytes()
    (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").write_bytes(content.replace(b"\n", b"\r\n"))
    sync_contributor_docs.main(check=True)


def test_the_gate_self_skips_without_the_lane_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "workflows" / "integrate.yml").write_text("on: {}\n", encoding="utf-8")
    sync_contributor_docs.main(check=True)
    assert not (tmp_path / "CONTRIBUTING.md").exists()


def test_write_mode_copies_the_canonical_verbatim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    lane_tree(tmp_path)
    sync_contributor_docs.main(check=False)
    assert (tmp_path / "CONTRIBUTING.md").read_bytes() == sync_contributor_docs.CONTRIBUTING_SOURCE.read_bytes()
    assert (
        tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md"
    ).read_bytes() == sync_contributor_docs.TEMPLATE_SOURCE.read_bytes()
