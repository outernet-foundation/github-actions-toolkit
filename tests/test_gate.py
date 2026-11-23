import json
from subprocess import CalledProcessError

import pytest

from github_actions_toolkit import merging as merging_module
from github_actions_toolkit.merging import PR_VIEW_FIELDS
from github_actions_toolkit.verbs import gate

CANDIDATE_REF = "refs/heads/candidate/7"
TESTED_TAG = "tested/7"
TESTED_SHA = "e" * 40


class CommandResponses:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def __call__(self, command: str) -> str:
        return self.responses[command]


class SequencedResponses:
    def __init__(self, responses: dict[str, str], sequence: dict[str, list[str]]) -> None:
        self.responses = responses
        self.sequence = sequence

    def __call__(self, command: str) -> str:
        queued = self.sequence.get(command)
        if queued:
            return queued.pop(0)
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


def gate_responses(labels: list[str]) -> dict[str, str]:
    return {
        f"gh pr view 7 --json {PR_VIEW_FIELDS}": pr_view_response(labels),
        "git merge-base FETCH_HEAD HEAD": "c" * 40 + "\n",
    }


def reuse_responses(labels: list[str], rebased_tree: str, tested_tree: str) -> dict[str, str]:
    responses = gate_responses(labels)
    responses["git rev-parse HEAD^{tree}"] = rebased_tree + "\n"
    responses[f"git rev-parse refs/tags/{TESTED_TAG}^{{tree}}"] = tested_tree + "\n"
    responses[f"git rev-parse refs/tags/{TESTED_TAG}"] = TESTED_SHA + "\n"
    return responses


def exit_message(exit_request: SystemExit) -> str:
    return str(exit_request.code)


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, str],
    dry_run: bool = False,
    bash_check_fn: CheckLog | None = None,
) -> tuple[SystemExit | None, BashLog, CheckLog]:
    bash_log = BashLog()
    check_log = patch_gate(monkeypatch, bash_log, responses, bash_check_fn)
    try:
        gate.main(dry_run=dry_run)
    except SystemExit as exit_request:
        return exit_request, bash_log, check_log
    return None, bash_log, check_log


def patch_gate(
    monkeypatch: pytest.MonkeyPatch,
    bash_function: object,
    responses: dict[str, str],
    bash_check_fn: CheckLog | None = None,
) -> CheckLog:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.delenv("PR_EVENT_ACTION", raising=False)
    monkeypatch.setattr(gate, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(merging_module, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(gate, "bash", bash_function)
    check_log = bash_check_fn or CheckLog(False)
    monkeypatch.setattr(gate, "bash_check", check_log)
    return check_log


def test_gate_rebuilds_the_head_onto_the_dev_tip_and_pushes_the_candidate_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, bash_log, _ = run_gate(monkeypatch, gate_responses(["approved-for-rebase-integrate"]))
    assert exit_request is None
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)
    assert any(f"git rebase --onto FETCH_HEAD {'c' * 40} HEAD" in command for command in bash_log.commands)
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)


def test_gate_takes_the_rebase_path_under_the_merge_label_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, bash_log, _ = run_gate(monkeypatch, gate_responses(["approved-for-merge"]))
    assert exit_request is None
    assert any(f"git rebase --onto FETCH_HEAD {'c' * 40} HEAD" in command for command in bash_log.commands)


def test_gate_idles_without_a_ci_label(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    exit_request, bash_log, _ = run_gate(monkeypatch, gate_responses([]))
    assert exit_request is None
    assert bash_log.commands == []
    output = capsys.readouterr().out
    assert "idling" in output
    assert "mode=idle" in output


def test_gate_pushes_the_head_as_is_under_the_plain_label(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, _ = run_gate(monkeypatch, gate_responses(["approved-for-integrate"]))
    assert exit_request is None
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert not any("fetch origin refs/heads/dev" in command for command in bash_log.commands)
    assert not any("git rebase" in command for command in bash_log.commands)
    assert "mode=full" in capsys.readouterr().out


def test_gate_refuses_the_as_is_label_stacked_on_the_rebase_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, bash_log, _ = run_gate(
        monkeypatch, gate_responses(["approved-for-integrate", "approved-for-rebase-integrate"])
    )
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "approved-for-integrate" in message
    assert "approved-for-rebase-integrate" in message
    assert not any("push" in command for command in bash_log.commands)


def test_gate_refuses_the_as_is_label_stacked_on_the_merge_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, _, _ = run_gate(monkeypatch, gate_responses(["approved-for-integrate", "approved-for-merge"]))
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "approved-for-integrate" in message
    assert "approved-for-merge" in message


def test_gate_dry_run_reports_the_contradiction_informationally(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, _ = run_gate(
        monkeypatch, gate_responses(["approved-for-integrate", "approved-for-merge"]), dry_run=True
    )
    assert exit_request is None
    assert "would abort" in capsys.readouterr().out
    assert bash_log.commands == []


def test_gate_conflict_aborts_with_the_conflicted_paths_and_teaches_the_as_is_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = gate_responses(["approved-for-rebase-integrate"])
    responses["git diff --name-only --diff-filter=U"] = "src/conflicted.py\n"
    failing = FailingBashLog(fail_on="git rebase --onto")
    patch_gate(monkeypatch, failing, responses)
    exit_request = None
    try:
        gate.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "conflicts" in message
    assert "src/conflicted.py" in message
    assert "approved-for-integrate" in message
    assert any("git rebase --abort" in command for command in failing.commands)
    assert not any(f"+HEAD:{CANDIDATE_REF}" in command for command in failing.commands)


def test_gate_configures_git_identity_before_the_rebase(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_request, bash_log, _ = run_gate(monkeypatch, gate_responses(["approved-for-rebase-integrate"]))
    assert exit_request is None
    commands = bash_log.commands
    name_index = next(i for i, command in enumerate(commands) if "user.name" in command)
    email_index = next(i for i, command in enumerate(commands) if "user.email" in command)
    rebase_index = next(i for i, command in enumerate(commands) if "git rebase --onto" in command)
    assert name_index < rebase_index
    assert email_index < rebase_index


def test_gate_dry_run_names_the_probe_and_candidate_ref_without_side_effects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, check_log = run_gate(
        monkeypatch, gate_responses(["approved-for-rebase-integrate"]), dry_run=True
    )
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)
    assert not any("git rebase" in command for command in bash_log.commands)
    assert check_log.commands == []
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)
    assert "would rebuild PR #7 onto the dev tip, probe the tested marker for reuse" in capsys.readouterr().out


def test_gate_refuses_a_ref_without_a_pr_number(monkeypatch: pytest.MonkeyPatch) -> None:
    bash_log = BashLog()
    patch_gate(monkeypatch, bash_log, {})
    monkeypatch.setenv("GITHUB_REF", "refs/heads/dev")
    exit_request = None
    try:
        gate.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is not None
    assert "carries no PR number" in exit_message(exit_request)


def test_gate_keeps_the_tested_candidate_when_the_marker_tree_matches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, check_log = run_gate(
        monkeypatch, reuse_responses(["approved-for-merge"], "tree1", "tree1"), bash_check_fn=CheckLog(True)
    )
    assert exit_request is None
    assert any(
        f"fetch origin +refs/tags/{TESTED_TAG}:refs/tags/{TESTED_TAG}" in command for command in check_log.commands
    )
    assert any(f"push origin +{TESTED_SHA}:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert not any(f"+HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert "mode=reuse" in capsys.readouterr().out


def test_gate_pushes_the_fresh_rebase_when_the_marker_tree_differs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = reuse_responses(["approved-for-merge"], "tree1", "tree2")
    exit_request, bash_log, _ = run_gate(monkeypatch, responses, bash_check_fn=CheckLog(True))
    assert exit_request is None
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert not any(f"+{TESTED_SHA}:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert "mode=full" in capsys.readouterr().out


def test_gate_treats_an_absent_marker_as_the_first_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, check_log = run_gate(
        monkeypatch, gate_responses(["approved-for-merge"]), bash_check_fn=CheckLog(False)
    )
    assert exit_request is None
    assert any(
        f"fetch origin +refs/tags/{TESTED_TAG}:refs/tags/{TESTED_TAG}" in command for command in check_log.commands
    )
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert "mode=full" in capsys.readouterr().out


def test_gate_strips_approval_labels_on_a_synchronize_wake_and_idles(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = gate_responses(["approved-for-merge", "approved-for-integrate"])
    sequenced = SequencedResponses(
        responses,
        {
            f"gh pr view 7 --json {PR_VIEW_FIELDS}": [
                responses[f"gh pr view 7 --json {PR_VIEW_FIELDS}"],
                pr_view_response([]),
            ]
        },
    )
    bash_log = BashLog()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("PR_EVENT_ACTION", "synchronize")
    monkeypatch.setattr(gate, "bash_output", sequenced)
    monkeypatch.setattr(merging_module, "bash_output", sequenced)
    monkeypatch.setattr(gate, "bash", bash_log)
    monkeypatch.setattr(gate, "bash_check", CheckLog(False))
    exit_request = None
    try:
        gate.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is None
    assert "gh pr edit 7 --remove-label approved-for-integrate" in bash_log.commands
    assert "gh pr edit 7 --remove-label approved-for-merge" in bash_log.commands
    assert sum("gh pr comment 7" in command for command in bash_log.commands) == 1
    assert not any("push origin" in command for command in bash_log.commands)
    output = capsys.readouterr().out
    assert "mode=idle" in output
    assert "revoked" in bash_log.commands[-1]


def test_gate_dry_run_reports_the_strip_informationally(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bash_log = BashLog()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("PR_EVENT_ACTION", "synchronize")
    monkeypatch.setattr(gate, "bash_output", CommandResponses(gate_responses(["approved-for-merge"])))
    monkeypatch.setattr(merging_module, "bash_output", CommandResponses(gate_responses(["approved-for-merge"])))
    monkeypatch.setattr(gate, "bash", bash_log)
    monkeypatch.setattr(gate, "bash_check", CheckLog(False))
    exit_request = None
    try:
        gate.main(dry_run=True)
    except SystemExit as request:
        exit_request = request
    assert exit_request is None
    assert bash_log.commands == []
    output = capsys.readouterr().out
    assert "would strip" in output
    assert "mode=idle" in output


def test_gate_does_not_strip_on_a_synchronize_wake_without_a_label(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bash_log = BashLog()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("PR_EVENT_ACTION", "synchronize")
    monkeypatch.setattr(gate, "bash_output", CommandResponses(gate_responses([])))
    monkeypatch.setattr(merging_module, "bash_output", CommandResponses(gate_responses([])))
    monkeypatch.setattr(gate, "bash", bash_log)
    monkeypatch.setattr(gate, "bash_check", CheckLog(False))
    exit_request = None
    try:
        gate.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is None
    assert bash_log.commands == []
    output = capsys.readouterr().out
    assert "idling" in output
    assert "mode=idle" in output
    assert "comment" not in " ".join(bash_log.commands)


def test_gate_does_not_strip_on_a_frozen_labeled_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("PR_EVENT_ACTION", "labeled")
    responses = gate_responses(["approved-for-merge"])
    bash_log = BashLog()
    monkeypatch.setattr(gate, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(merging_module, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(gate, "bash", bash_log)
    monkeypatch.setattr(gate, "bash_check", CheckLog(False))
    exit_request = None
    try:
        gate.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is None
    assert not any("remove-label" in command for command in bash_log.commands)
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)


def test_gate_does_not_strip_without_an_event_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("PR_EVENT_ACTION", "")
    responses = reuse_responses(["approved-for-merge"], "tree1", "tree1")
    bash_log = BashLog()
    monkeypatch.setattr(gate, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(merging_module, "bash_output", CommandResponses(responses))
    monkeypatch.setattr(gate, "bash", bash_log)
    monkeypatch.setattr(gate, "bash_check", CheckLog(True))
    exit_request = None
    try:
        gate.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is None
    assert not any("remove-label" in command for command in bash_log.commands)
