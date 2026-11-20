import pytest

from github_actions_toolkit.verbs import retry

RUN_ID = "4242"
RUN_STATUS_URL = f"gh api repos/owner/repo/actions/runs/{RUN_ID} --jq .status"
RERUN_URL = f"gh api -X POST repos/owner/repo/actions/runs/{RUN_ID}/rerun"


class StatusSequence:
    def __init__(self, statuses: list[str]) -> None:
        self.statuses = statuses
        self.calls = 0

    def __call__(self, command: str) -> str:
        assert command == RUN_STATUS_URL
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return status


class BashLog:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def __call__(self, command: str, **kwargs: object) -> None:
        self.commands.append(command)


def exit_message(exit_request: SystemExit) -> str:
    return str(exit_request.code)


def patch_retry(
    monkeypatch: pytest.MonkeyPatch,
    statuses: list[str],
    bash_function: object,
) -> BashLog:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("RUN_ID", RUN_ID)
    monkeypatch.setattr(retry, "bash_output", StatusSequence(statuses))
    bash_log = BashLog()
    monkeypatch.setattr(retry, "bash", bash_function if bash_function else bash_log)
    return bash_log


def noop_sleep(_seconds: float) -> None:
    return None


def test_retry_polls_until_completed_then_reruns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry.time, "sleep", noop_sleep)
    bash_log = patch_retry(monkeypatch, ["in_progress", "in_progress", "completed"], None)
    exit_request = None
    try:
        retry.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is None
    assert bash_log.commands == [RERUN_URL]


def test_retry_reruns_a_completed_run_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    bash_log = patch_retry(monkeypatch, ["completed"], None)
    exit_request = None
    try:
        retry.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is None
    assert bash_log.commands == [RERUN_URL]


def test_retry_dry_run_fetches_once_and_reports(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    statuses = StatusSequence(["in_progress"])
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("RUN_ID", RUN_ID)
    monkeypatch.setattr(retry, "bash_output", statuses)
    bash_log = BashLog()
    monkeypatch.setattr(retry, "bash", bash_log)
    exit_request = None
    try:
        retry.main(dry_run=True)
    except SystemExit as request:
        exit_request = request
    assert exit_request is None
    assert bash_log.commands == []
    assert statuses.calls == 1
    assert "would re-run run 4242 once it completes" in capsys.readouterr().out


def test_retry_requires_the_run_id_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.delenv("RUN_ID", raising=False)
    exit_request = None
    try:
        retry.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is not None
    assert "RUN_ID" in exit_message(exit_request)
