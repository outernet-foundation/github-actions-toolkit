import json

import pytest

from github_actions_toolkit import releases as releases_module
from github_actions_toolkit.verbs import cleanup_pr_releases


class BashLog:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def __call__(self, command: str) -> None:
        self.commands.append(command)


def patch_sweep_context(monkeypatch: pytest.MonkeyPatch, tag_names: list[str]) -> BashLog:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")

    def listing(command: str) -> str:
        return json.dumps([{"tagName": name} for name in tag_names])

    monkeypatch.setattr(releases_module, "bash_output", listing)
    bash_log = BashLog()
    monkeypatch.setattr(releases_module, "bash", bash_log)
    return bash_log


def test_cleanup_sweeps_the_prs_run_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    bash_log = patch_sweep_context(monkeypatch, ["pr-107-1560", "pr-107-1563", "dev-1563"])

    cleanup_pr_releases.main(pr_number=107)

    assert bash_log.commands == [
        "gh release delete pr-107-1560 --cleanup-tag --yes --repo owner/repo",
        "gh release delete pr-107-1563 --cleanup-tag --yes --repo owner/repo",
    ]


def test_cleanup_spares_other_prefixes_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    bash_log = patch_sweep_context(monkeypatch, ["pr-1070-5", "pr-107-1563"])

    cleanup_pr_releases.main(pr_number=107)

    assert bash_log.commands == ["gh release delete pr-107-1563 --cleanup-tag --yes --repo owner/repo"]


def test_cleanup_is_idempotent_without_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    bash_log = patch_sweep_context(monkeypatch, [])

    cleanup_pr_releases.main(pr_number=107)

    assert bash_log.commands == []


def test_cleanup_requires_the_runner_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_ACTOR", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)

    with pytest.raises(SystemExit):
        cleanup_pr_releases.main(pr_number=107)
