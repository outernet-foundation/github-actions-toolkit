from subprocess import CalledProcessError

import pytest

from github_actions_toolkit.verbs import rebase

HEAD_SHA = "a" * 40
CANDIDATE_REF = "refs/heads/candidate/7"


class CommandResponses:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def __call__(self, command: str) -> str:
        return self.responses[command]


class BashLog:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def __call__(self, command: str, **kwargs: object) -> None:
        self.commands.append(command)


class FailingBashLog:
    def __init__(self, fail_on: str) -> None:
        self.fail_on = fail_on
        self.commands: list[str] = []

    def __call__(self, command: str, **kwargs: object) -> None:
        self.commands.append(command)
        if self.fail_on in command:
            raise CalledProcessError(returncode=1, cmd=command)


def rebase_responses() -> dict[str, str]:
    return {
        "git merge-base FETCH_HEAD HEAD": "c" * 40 + "\n",
    }


def exit_message(exit_request: SystemExit) -> str:
    return str(exit_request.code)


def patch_rebase(
    monkeypatch: pytest.MonkeyPatch,
    bash_function: object,
    responses: dict[str, str],
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setattr(rebase, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(rebase, "bash", bash_function)


def run_rebase(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, str],
    dry_run: bool = False,
) -> tuple[SystemExit | None, BashLog]:
    bash_log = BashLog()
    patch_rebase(monkeypatch, bash_log, responses)
    try:
        rebase.main(dry_run=dry_run)
    except SystemExit as exit_request:
        return exit_request, bash_log
    return None, bash_log


def test_rebase_rebuilds_the_head_onto_the_dev_tip_and_pushes_the_candidate_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, bash_log = run_rebase(monkeypatch, rebase_responses())
    assert exit_request is None
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)
    assert any(f"git rebase --onto FETCH_HEAD {'c' * 40} HEAD" in command for command in bash_log.commands)
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)


def test_rebase_conflict_aborts_with_the_conflicted_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = rebase_responses()
    responses["git diff --name-only --diff-filter=U"] = "src/conflicted.py\n"
    failing = FailingBashLog(fail_on="git rebase --onto")
    patch_rebase(monkeypatch, failing, responses)
    exit_request = None
    try:
        rebase.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "conflicts" in message
    assert "src/conflicted.py" in message
    assert any("git rebase --abort" in command for command in failing.commands)
    assert not any(f"+HEAD:{CANDIDATE_REF}" in command for command in failing.commands)


def test_rebase_configures_git_identity_before_the_rebase(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_request, bash_log = run_rebase(monkeypatch, rebase_responses())
    assert exit_request is None
    commands = bash_log.commands
    name_index = next(i for i, command in enumerate(commands) if "user.name" in command)
    email_index = next(i for i, command in enumerate(commands) if "user.email" in command)
    rebase_index = next(i for i, command in enumerate(commands) if "git rebase --onto" in command)
    assert name_index < rebase_index
    assert email_index < rebase_index


def test_rebase_dry_run_names_the_candidate_ref_without_side_effects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log = run_rebase(monkeypatch, rebase_responses(), dry_run=True)
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)
    assert not any("git rebase" in command for command in bash_log.commands)
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)
    assert "would rebuild PR #7 onto the dev tip and force-push refs/heads/candidate/7" in capsys.readouterr().out


def test_rebase_refuses_a_ref_without_a_pr_number(monkeypatch: pytest.MonkeyPatch) -> None:
    bash_log = BashLog()
    patch_rebase(monkeypatch, bash_log, {})
    monkeypatch.setenv("GITHUB_REF", "refs/heads/dev")
    exit_request = None
    try:
        rebase.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is not None
    assert "carries no PR number" in exit_message(exit_request)
