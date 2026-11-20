import json
from subprocess import CalledProcessError

import pytest

from github_actions_toolkit import pull_requests as pull_requests_module
from github_actions_toolkit.pull_requests import PR_VIEW_FIELDS
from github_actions_toolkit.verbs import rebase

CANDIDATE_REF = "refs/heads/candidate/7"
TESTED_TAG = "tested/7"
TESTED_SHA = "e" * 40


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


class CheckLog:
    def __init__(self, succeed: bool) -> None:
        self.succeed = succeed
        self.commands: list[str] = []

    def __call__(self, command: str) -> bool:
        self.commands.append(command)
        return self.succeed


def pr_view_response(labels: list[str]) -> str:
    return json.dumps({
        "state": "OPEN",
        "title": "Test PR",
        "headRefOid": "a" * 40,
        "headRefName": "feature-x",
        "baseRefName": "dev",
        "labels": [{"name": name} for name in labels],
        "isDraft": False,
    })


def rebase_responses(labels: list[str]) -> dict[str, str]:
    return {
        f"gh pr view 7 --json {PR_VIEW_FIELDS}": pr_view_response(labels),
        "git merge-base FETCH_HEAD HEAD": "c" * 40 + "\n",
    }


def reuse_responses(labels: list[str], rebased_tree: str, tested_tree: str) -> dict[str, str]:
    responses = rebase_responses(labels)
    responses["git rev-parse HEAD^{tree}"] = rebased_tree + "\n"
    responses[f"git rev-parse refs/tags/{TESTED_TAG}^{{tree}}"] = tested_tree + "\n"
    responses[f"git rev-parse refs/tags/{TESTED_TAG}"] = TESTED_SHA + "\n"
    return responses


def exit_message(exit_request: SystemExit) -> str:
    return str(exit_request.code)


def patch_rebase(
    monkeypatch: pytest.MonkeyPatch,
    bash_function: object,
    responses: dict[str, str],
    bash_check_fn: CheckLog | None = None,
) -> CheckLog:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setattr(rebase, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(pull_requests_module, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(rebase, "bash", bash_function)
    check_log = bash_check_fn or CheckLog(False)
    monkeypatch.setattr(rebase, "bash_check", check_log)
    return check_log


def run_rebase(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, str],
    dry_run: bool = False,
    bash_check_fn: CheckLog | None = None,
) -> tuple[SystemExit | None, BashLog, CheckLog]:
    bash_log = BashLog()
    check_log = patch_rebase(monkeypatch, bash_log, responses, bash_check_fn)
    try:
        rebase.main(dry_run=dry_run)
    except SystemExit as exit_request:
        return exit_request, bash_log, check_log
    return None, bash_log, check_log


def test_rebase_rebuilds_the_head_onto_the_dev_tip_and_pushes_the_candidate_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, bash_log, _ = run_rebase(monkeypatch, rebase_responses(["ready-to-rebase-integrate"]))
    assert exit_request is None
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)
    assert any(f"git rebase --onto FETCH_HEAD {'c' * 40} HEAD" in command for command in bash_log.commands)
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)


def test_rebase_takes_the_rebase_path_under_the_merge_label_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, bash_log, _ = run_rebase(monkeypatch, rebase_responses(["ready-to-merge"]))
    assert exit_request is None
    assert any(f"git rebase --onto FETCH_HEAD {'c' * 40} HEAD" in command for command in bash_log.commands)


def test_rebase_idles_without_a_ci_label(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    exit_request, bash_log, _ = run_rebase(monkeypatch, rebase_responses([]))
    assert exit_request is None
    assert bash_log.commands == []
    output = capsys.readouterr().out
    assert "idling" in output
    assert "mode=idle" in output


def test_rebase_pushes_the_head_as_is_under_the_plain_label(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, _ = run_rebase(monkeypatch, rebase_responses(["ready-to-integrate"]))
    assert exit_request is None
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert not any("fetch origin refs/heads/dev" in command for command in bash_log.commands)
    assert not any("git rebase" in command for command in bash_log.commands)
    assert "mode=full" in capsys.readouterr().out


def test_rebase_refuses_the_as_is_label_stacked_on_the_rebase_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, bash_log, _ = run_rebase(
        monkeypatch, rebase_responses(["ready-to-integrate", "ready-to-rebase-integrate"])
    )
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "ready-to-integrate" in message
    assert "ready-to-rebase-integrate" in message
    assert not any("push" in command for command in bash_log.commands)


def test_rebase_refuses_the_as_is_label_stacked_on_the_merge_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, _, _ = run_rebase(monkeypatch, rebase_responses(["ready-to-integrate", "ready-to-merge"]))
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "ready-to-integrate" in message
    assert "ready-to-merge" in message


def test_rebase_dry_run_reports_the_contradiction_informationally(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, _ = run_rebase(
        monkeypatch, rebase_responses(["ready-to-integrate", "ready-to-merge"]), dry_run=True
    )
    assert exit_request is None
    assert "would abort" in capsys.readouterr().out
    assert bash_log.commands == []


def test_rebase_conflict_aborts_with_the_conflicted_paths_and_teaches_the_as_is_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = rebase_responses(["ready-to-rebase-integrate"])
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
    assert "ready-to-integrate" in message
    assert any("git rebase --abort" in command for command in failing.commands)
    assert not any(f"+HEAD:{CANDIDATE_REF}" in command for command in failing.commands)


def test_rebase_configures_git_identity_before_the_rebase(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_request, bash_log, _ = run_rebase(monkeypatch, rebase_responses(["ready-to-rebase-integrate"]))
    assert exit_request is None
    commands = bash_log.commands
    name_index = next(i for i, command in enumerate(commands) if "user.name" in command)
    email_index = next(i for i, command in enumerate(commands) if "user.email" in command)
    rebase_index = next(i for i, command in enumerate(commands) if "git rebase --onto" in command)
    assert name_index < rebase_index
    assert email_index < rebase_index


def test_rebase_dry_run_names_the_probe_and_candidate_ref_without_side_effects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, check_log = run_rebase(
        monkeypatch, rebase_responses(["ready-to-rebase-integrate"]), dry_run=True
    )
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)
    assert not any("git rebase" in command for command in bash_log.commands)
    assert check_log.commands == []
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)
    assert "would rebuild PR #7 onto the dev tip, probe the tested marker for reuse" in capsys.readouterr().out


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


def test_rebase_keeps_the_tested_candidate_when_the_marker_tree_matches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, check_log = run_rebase(
        monkeypatch, reuse_responses(["ready-to-merge"], "tree1", "tree1"), bash_check_fn=CheckLog(True)
    )
    assert exit_request is None
    assert any(
        f"fetch origin +refs/tags/{TESTED_TAG}:refs/tags/{TESTED_TAG}" in command for command in check_log.commands
    )
    assert any(f"push origin +{TESTED_SHA}:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert not any(f"+HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert "mode=reuse" in capsys.readouterr().out


def test_rebase_pushes_the_fresh_rebase_when_the_marker_tree_differs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = reuse_responses(["ready-to-merge"], "tree1", "tree2")
    exit_request, bash_log, _ = run_rebase(monkeypatch, responses, bash_check_fn=CheckLog(True))
    assert exit_request is None
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert not any(f"+{TESTED_SHA}:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert "mode=full" in capsys.readouterr().out


def test_rebase_treats_an_absent_marker_as_the_first_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, check_log = run_rebase(
        monkeypatch, rebase_responses(["ready-to-merge"]), bash_check_fn=CheckLog(False)
    )
    assert exit_request is None
    assert any(
        f"fetch origin +refs/tags/{TESTED_TAG}:refs/tags/{TESTED_TAG}" in command for command in check_log.commands
    )
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert "mode=full" in capsys.readouterr().out
