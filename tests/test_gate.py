import json
import shlex
from subprocess import CalledProcessError

import pytest

from github_actions_toolkit import merging as merging_module
from github_actions_toolkit.merging import PR_VIEW_FIELDS
from github_actions_toolkit.verbs import gate

CANDIDATE_REF = "refs/heads/candidate/7"
TESTED_TAG = "tested/7"
TESTED_SHA = "e" * 40
HEAD_SHA = "a" * 40
AUTHOR = "maintainer"
REVIEWER = "reviewer"
OUTSIDER = "outsider"
READER = "reader"
STRANGER = "stranger"
VIEW_COMMAND = f"gh pr view 7 --json {PR_VIEW_FIELDS}"
REVIEWS_COMMAND = "gh api repos/owner/repo/pulls/7/reviews --paginate --slurp"
EARLIER = "2026-11-22T09:00:00Z"
LATER = "2026-11-22T10:00:00Z"


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
    def __init__(self, fail_on: str = "") -> None:
        self.fail_on = fail_on
        self.commands: list[str] = []

    def __call__(self, command: str, **kwargs: object) -> None:
        self.commands.append(command)
        if self.fail_on and self.fail_on in command:
            raise CalledProcessError(returncode=1, cmd=command)


class CheckLog:
    def __init__(self, succeed: bool) -> None:
        self.succeed = succeed
        self.commands: list[str] = []

    def __call__(self, command: str) -> bool:
        self.commands.append(command)
        return self.succeed


class PermissionCheck:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.commands: list[str] = []

    def __call__(self, command: str) -> bool:
        self.commands.append(command)
        return command in self.responses


def permission_command(login: str) -> str:
    return f"gh api repos/owner/repo/collaborators/{login}/permission"


def pr_view_response(labels: list[str], author: str = AUTHOR) -> str:
    return json.dumps({
        "state": "OPEN",
        "title": "Test PR",
        "author": {"login": author},
        "headRefOid": HEAD_SHA,
        "headRefName": "feature-x",
        "baseRefName": "dev",
        "labels": [{"name": name} for name in labels],
        "isDraft": False,
    })


def review(
    review_id: int,
    login: str,
    state: str,
    commit_id: str = HEAD_SHA,
    submitted_at: str | None = LATER,
) -> dict[str, object]:
    return {
        "id": review_id,
        "state": state,
        "commit_id": commit_id,
        "submitted_at": submitted_at,
        "user": {"login": login},
    }


def gate_responses(
    labels: list[str], author: str = AUTHOR, reviews: list[dict[str, object]] | None = None
) -> dict[str, str]:
    responses: dict[str, str] = {
        VIEW_COMMAND: pr_view_response(labels, author),
        "git merge-base FETCH_HEAD HEAD": "c" * 40 + "\n",
        permission_command(AUTHOR): json.dumps({"permission": "write", "role_name": "write"}),
        permission_command(REVIEWER): json.dumps({"permission": "write", "role_name": "write"}),
        permission_command(READER): json.dumps({"permission": "read", "role_name": "read"}),
    }
    if reviews is not None:
        responses["git rev-parse HEAD"] = HEAD_SHA + "\n"
        responses[REVIEWS_COMMAND] = json.dumps([reviews])
    return responses


def reuse_responses(
    labels: list[str],
    rebased_tree: str,
    tested_tree: str,
    author: str = AUTHOR,
    reviews: list[dict[str, object]] | None = None,
) -> dict[str, str]:
    responses = gate_responses(labels, author=author, reviews=reviews)
    responses["git rev-parse HEAD^{tree}"] = rebased_tree + "\n"
    responses[f"git rev-parse refs/tags/{TESTED_TAG}^{{tree}}"] = tested_tree + "\n"
    responses[f"git rev-parse refs/tags/{TESTED_TAG}"] = TESTED_SHA + "\n"
    return responses


def exit_message(exit_request: SystemExit) -> str:
    return str(exit_request.code)


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, str] | CommandResponses | SequencedResponses,
    dry_run: bool = False,
    bash_check_fn: CheckLog | None = None,
    event_action: str | None = None,
    fail_on: str = "",
) -> tuple[SystemExit | None, BashLog, CheckLog]:
    bash_log, check_log = patch_gate(
        monkeypatch,
        responses,
        bash_check_fn=bash_check_fn,
        event_action=event_action,
        fail_on=fail_on,
    )
    try:
        gate.main(dry_run=dry_run)
    except SystemExit as exit_request:
        return exit_request, bash_log, check_log
    return None, bash_log, check_log


def patch_gate(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, str] | CommandResponses | SequencedResponses,
    bash_check_fn: CheckLog | None = None,
    event_action: str | None = None,
    fail_on: str = "",
) -> tuple[BashLog, CheckLog]:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    if event_action is not None:
        monkeypatch.setenv("PR_EVENT_ACTION", event_action)
    if event_action is None:
        monkeypatch.delenv("PR_EVENT_ACTION", raising=False)
    responder = CommandResponses(responses) if isinstance(responses, dict) else responses
    bash_log = BashLog(fail_on=fail_on)
    monkeypatch.setattr(gate, "bash_output", responder)
    monkeypatch.setattr(merging_module, "bash_output", responder)
    monkeypatch.setattr(gate, "bash", bash_log)
    check_log = bash_check_fn or CheckLog(False)
    monkeypatch.setattr(gate, "bash_check", check_log)
    monkeypatch.setattr(merging_module, "bash_check", PermissionCheck(responder.responses))
    return bash_log, check_log


REFUSED_HEADS: dict[str, tuple[list[dict[str, object]], str]] = {
    "changes_requested": ([review(1, REVIEWER, "CHANGES_REQUESTED")], "is CHANGES_REQUESTED"),
    "commented": ([review(1, REVIEWER, "COMMENTED")], "is COMMENTED"),
    "dismissed": ([review(1, REVIEWER, "DISMISSED")], "is DISMISSED"),
    "newer_changes_requested": (
        [review(1, REVIEWER, "APPROVED", submitted_at=EARLIER), review(2, REVIEWER, "CHANGES_REQUESTED")],
        "is CHANGES_REQUESTED",
    ),
    "no_review": ([], "no write actor has reviewed head"),
    "review_at_another_commit": (
        [review(1, REVIEWER, "APPROVED", commit_id="d" * 40)],
        "no write actor has reviewed head",
    ),
    "pending_only": ([review(1, REVIEWER, "PENDING", submitted_at=None)], "no write actor has reviewed head"),
    "strangers_approval_only": ([review(1, OUTSIDER, "APPROVED")], "no write actor has reviewed head"),
    "read_only_approval_only": ([review(1, READER, "APPROVED")], "no write actor has reviewed head"),
}


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


def test_gate_refuses_the_stacked_pair_before_the_review_anchor(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_request, bash_log, _ = run_gate(
        monkeypatch, gate_responses(["approved-for-integrate", "approved-for-merge"], author=STRANGER)
    )
    assert exit_request is not None
    assert "never merges" in exit_message(exit_request)
    assert bash_log.commands == []


def test_gate_conflict_aborts_with_the_conflicted_paths_and_teaches_the_as_is_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = gate_responses(["approved-for-rebase-integrate"])
    responses["git diff --name-only --diff-filter=U"] = "src/conflicted.py\n"
    exit_request, failing, _ = run_gate(monkeypatch, responses, fail_on="git rebase --onto")
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
    patch_gate(monkeypatch, {})
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
    sequenced = SequencedResponses(responses, {VIEW_COMMAND: [responses[VIEW_COMMAND], pr_view_response([])]})
    exit_request, bash_log, _ = run_gate(monkeypatch, sequenced, event_action="synchronize")
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
    exit_request, bash_log, _ = run_gate(
        monkeypatch, gate_responses(["approved-for-merge"]), dry_run=True, event_action="synchronize"
    )
    assert exit_request is None
    assert bash_log.commands == []
    output = capsys.readouterr().out
    assert "would strip" in output
    assert "mode=idle" in output


def test_gate_does_not_strip_on_a_synchronize_wake_without_a_label(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_request, bash_log, _ = run_gate(monkeypatch, gate_responses([]), event_action="synchronize")
    assert exit_request is None
    assert bash_log.commands == []
    output = capsys.readouterr().out
    assert "idling" in output
    assert "mode=idle" in output
    assert "comment" not in " ".join(bash_log.commands)


def test_gate_does_not_strip_on_a_frozen_labeled_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_request, bash_log, _ = run_gate(monkeypatch, gate_responses(["approved-for-merge"]), event_action="labeled")
    assert exit_request is None
    assert not any("remove-label" in command for command in bash_log.commands)
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)


def test_gate_does_not_strip_without_an_event_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = reuse_responses(["approved-for-merge"], "tree1", "tree1")
    exit_request, bash_log, _ = run_gate(monkeypatch, responses, bash_check_fn=CheckLog(True), event_action="")
    assert exit_request is None
    assert not any("remove-label" in command for command in bash_log.commands)


def test_gate_passes_on_an_approving_review_at_the_head(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(
        ["approved-for-rebase-integrate"], author=STRANGER, reviews=[review(1, REVIEWER, "APPROVED")]
    )
    exit_request, bash_log, _ = run_gate(monkeypatch, responses)
    assert exit_request is None
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)


@pytest.mark.parametrize(("reviews", "verdict"), list(REFUSED_HEADS.values()), ids=list(REFUSED_HEADS))
def test_gate_refuses_a_labeled_head_no_write_actor_has_approved(
    monkeypatch: pytest.MonkeyPatch, reviews: list[dict[str, object]], verdict: str
) -> None:
    responses = gate_responses(["approved-for-merge"], author=STRANGER, reviews=reviews)
    exit_request, bash_log, check_log = run_gate(monkeypatch, responses)
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "PR #7 carries an approval label" in message
    assert verdict in message
    assert "then applies the label again" in message
    assert check_log.commands == []
    assert not any("push" in command or "fetch" in command for command in bash_log.commands)


def test_gate_refusal_strips_every_label_and_posts_the_teaching_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = ["approved-for-merge", "approved-for-rebase-integrate"]
    exit_request, bash_log, _ = run_gate(monkeypatch, gate_responses(labels, author=STRANGER, reviews=[]))
    assert exit_request is not None
    assert "gh pr edit 7 --remove-label approved-for-merge" in bash_log.commands
    assert "gh pr edit 7 --remove-label approved-for-rebase-integrate" in bash_log.commands
    assert sum("gh pr comment 7" in command for command in bash_log.commands) == 1
    assert f"gh pr comment 7 --body {shlex.quote(gate.ANCHOR_COMMENT)}" in bash_log.commands


def test_gate_dry_run_reports_the_review_refusal_informationally(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = gate_responses(["approved-for-merge"], author=STRANGER, reviews=[])
    exit_request, bash_log, _ = run_gate(monkeypatch, responses, dry_run=True)
    assert exit_request is None
    assert bash_log.commands == []
    output = capsys.readouterr().out
    assert "would refuse" in output
    assert "then applies the label again" in output
    assert "would strip ['approved-for-merge'] from PR #7" in output


def test_gate_ignores_a_pending_review_newer_than_the_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(
        ["approved-for-merge"],
        author=STRANGER,
        reviews=[
            review(1, REVIEWER, "APPROVED", submitted_at=EARLIER),
            review(2, REVIEWER, "PENDING", submitted_at=None),
        ],
    )
    exit_request, _, _ = run_gate(monkeypatch, responses)
    assert exit_request is None


def test_gate_takes_the_newer_approval_over_an_older_changes_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(
        ["approved-for-merge"],
        author=STRANGER,
        reviews=[
            review(1, REVIEWER, "CHANGES_REQUESTED", submitted_at=EARLIER),
            review(2, REVIEWER, "APPROVED"),
        ],
    )
    exit_request, _, _ = run_gate(monkeypatch, responses)
    assert exit_request is None


@pytest.mark.parametrize(
    ("reviews", "passes"),
    [
        ([review(1, REVIEWER, "CHANGES_REQUESTED"), review(2, REVIEWER, "APPROVED")], True),
        ([review(1, REVIEWER, "APPROVED"), review(2, REVIEWER, "CHANGES_REQUESTED")], False),
    ],
    ids=["the_later_id_approves", "the_later_id_requests_changes"],
)
def test_gate_breaks_a_submitted_at_tie_by_the_later_review_id(
    monkeypatch: pytest.MonkeyPatch, reviews: list[dict[str, object]], passes: bool
) -> None:
    exit_request, _, _ = run_gate(monkeypatch, gate_responses(["approved-for-merge"], author=STRANGER, reviews=reviews))
    assert (exit_request is None) is passes


def test_gate_ignores_a_strangers_changes_requested(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = gate_responses(
        ["approved-for-merge"],
        author=STRANGER,
        reviews=[
            review(1, REVIEWER, "APPROVED", submitted_at=EARLIER),
            review(2, OUTSIDER, "CHANGES_REQUESTED"),
        ],
    )
    exit_request, bash_log, _ = run_gate(monkeypatch, responses)
    assert exit_request is None
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert "reviewer approved head aaaaaaaaaaaa" in capsys.readouterr().out


def test_gate_reads_every_review_page(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(["approved-for-merge"], author=STRANGER)
    responses["git rev-parse HEAD"] = HEAD_SHA + "\n"
    responses[REVIEWS_COMMAND] = json.dumps([[review(1, OUTSIDER, "APPROVED")], [review(2, REVIEWER, "APPROVED")]])
    exit_request, _, _ = run_gate(monkeypatch, responses)
    assert exit_request is None


@pytest.mark.parametrize("permission", ["admin", "maintain", "write"])
def test_gate_exempts_a_write_actors_own_pr_without_reading_the_head_or_the_reviews(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], permission: str
) -> None:
    responses = gate_responses(["approved-for-merge"])
    responses[permission_command(AUTHOR)] = json.dumps({"permission": permission, "role_name": permission})
    exit_request, bash_log, _ = run_gate(monkeypatch, responses)
    assert exit_request is None
    assert any(f"push origin +HEAD:{CANDIDATE_REF}" in command for command in bash_log.commands)
    assert f"{AUTHOR} holds write permission" in capsys.readouterr().out


def test_gate_holds_a_read_only_author_to_the_review_check(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(["approved-for-merge"], author=READER, reviews=[])
    exit_request, _, _ = run_gate(monkeypatch, responses)
    assert exit_request is not None
    assert "no write actor has reviewed head" in exit_message(exit_request)


def test_gate_grants_no_exemption_when_the_permission_lookup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(["approved-for-merge"], author=STRANGER, reviews=[review(1, REVIEWER, "APPROVED")])
    exit_request, _, _ = run_gate(monkeypatch, responses)
    assert exit_request is None


def test_gate_anchors_the_reuse_path_before_the_marker_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = reuse_responses(["approved-for-merge"], "tree1", "tree1", author=STRANGER, reviews=[])
    exit_request, bash_log, check_log = run_gate(monkeypatch, responses, bash_check_fn=CheckLog(True))
    assert exit_request is not None
    assert check_log.commands == []
    assert not any("fetch origin" in command for command in bash_log.commands)


def test_gate_reuses_the_tested_candidate_once_a_review_anchors_the_head(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = reuse_responses(
        ["approved-for-merge"], "tree1", "tree1", author=STRANGER, reviews=[review(1, REVIEWER, "APPROVED")]
    )
    exit_request, _, _ = run_gate(monkeypatch, responses, bash_check_fn=CheckLog(True))
    assert exit_request is None
    assert "mode=reuse" in capsys.readouterr().out
