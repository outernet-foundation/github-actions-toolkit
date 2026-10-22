import json
from collections.abc import Callable, Mapping, Sequence
from subprocess import CalledProcessError

import pytest

from github_actions_toolkit.verbs import merge_gate

HEAD_SHA = "a" * 40
GREEN_RUNS = [{"name": "lint-workflows", "status": "completed", "conclusion": "success"}]


class CommandResponses:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def __call__(self, command: str) -> str:
        return self.responses[command]


class BashLog:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def __call__(self, command: str) -> None:
        self.commands.append(command)


def pr_view_payload(labels: list[str], state: str = "OPEN", title: str = "Test PR") -> str:
    return json.dumps({
        "state": state,
        "title": title,
        "headRefOid": HEAD_SHA,
        "labels": [{"name": name} for name in labels],
    })


def gate_responses(payload: str, runs: Sequence[Mapping[str, str | None]]) -> dict[str, str]:
    return {
        f"git branch -r --contains {HEAD_SHA}": "  origin/feature-x\n",
        "gh pr list --head feature-x --base dev --json number,headRefOid": json.dumps([
            {"number": 7, "headRefOid": HEAD_SHA}
        ]),
        "gh pr view 7 --json state,title,headRefOid,labels": payload,
        f"gh api repos/owner/repo/commits/{HEAD_SHA}/check-runs --paginate --slurp": json.dumps([
            {"total_count": len(runs), "check_runs": list(runs)}
        ]),
        "gh pr view 7 --json headRefName --jq .headRefName": "feature-x\n",
        "git rev-parse HEAD": f"{HEAD_SHA}\n",
    }


def accept_any_bash_check(command: str) -> bool:
    return True


def noop_sweep(prefix: str, repo: str) -> None:
    pass


def noop_install_oras() -> None:
    pass


def noop_promote(registry: str, name: str, pr_number: int) -> list[str]:
    return []


def exit_message(exit_request: SystemExit) -> str:
    return str(exit_request.code)


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, str],
    bash_check_fn: Callable[[str], bool] | None = None,
    delete_sweep_fn: Callable[[str, str], None] | None = None,
    promote_fn: Callable[[str, str, int], list[str]] | None = None,
    dry_run: bool = False,
) -> tuple[SystemExit | None, BashLog]:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setattr(merge_gate, "bash_output", CommandResponses(responses))
    bash_log = BashLog()
    monkeypatch.setattr(merge_gate, "bash", bash_log)
    monkeypatch.setattr(merge_gate, "bash_check", bash_check_fn or accept_any_bash_check)
    monkeypatch.setattr(merge_gate, "delete_releases_by_prefix", delete_sweep_fn or noop_sweep)
    monkeypatch.setattr(merge_gate, "install_oras", noop_install_oras)
    monkeypatch.setattr(merge_gate, "promote_scope", promote_fn or noop_promote)
    try:
        merge_gate.main(head_sha=HEAD_SHA, dry_run=dry_run)
    except SystemExit as exit_request:
        return exit_request, bash_log
    return None, bash_log


def test_gate_refuses_without_the_ready_to_merge_label(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload([]), GREEN_RUNS)
    exit_request, bash_log = run_gate(monkeypatch, responses)
    assert exit_request is not None
    assert "ready-to-merge" in exit_message(exit_request)
    assert not any("push" in command for command in bash_log.commands)


def test_gate_refuses_a_pr_that_is_not_open(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"], state="CLOSED")
    exit_request, _ = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS))
    assert exit_request is not None
    assert "not OPEN" in exit_message(exit_request)


def test_gate_refuses_terminal_check_failures_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = [{"name": "lint-workflows", "status": "completed", "conclusion": "failure"}]
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, runs))
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "checks not green" in message
    assert "PR #7" in message
    assert HEAD_SHA[:12] in message
    assert not any("push" in command for command in bash_log.commands)


def test_gate_refuses_loudly_while_checks_are_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = [
        {"name": "lint-workflows", "status": "completed", "conclusion": "success"},
        {"name": "preflight", "status": "in_progress"},
        {"name": "build", "status": "queued"},
    ]
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, runs))
    assert exit_request is not None
    assert "re-add" in exit_message(exit_request)
    assert not any("push" in command for command in bash_log.commands)


def test_gate_lands_a_labeled_green_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS))
    assert exit_request is None
    assert any("git merge --no-ff" in command for command in bash_log.commands)
    assert any("push origin HEAD:refs/heads/dev" in command for command in bash_log.commands)


def test_gate_configures_git_identity_before_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS))
    assert exit_request is None
    commands = bash_log.commands
    name_index = next(i for i, cmd in enumerate(commands) if "user.name" in cmd)
    email_index = next(i for i, cmd in enumerate(commands) if "user.email" in cmd)
    merge_index = next(i for i, cmd in enumerate(commands) if "git merge --no-ff" in cmd)
    assert name_index < merge_index
    assert email_index < merge_index


def test_gate_merge_message_includes_pr_title(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"], title="Add draft release surfaces")
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS))
    assert exit_request is None
    assert any("Merge PR #7: Add draft release surfaces" in command for command in bash_log.commands)


def test_gate_treats_skipped_checks_as_green(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = [
        {"name": "lint-workflows", "status": "completed", "conclusion": "success"},
        {"name": "unity-matrix", "status": "completed", "conclusion": "skipped"},
    ]
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, runs))
    assert exit_request is None
    assert any("push origin HEAD:refs/heads/dev" in command for command in bash_log.commands)


def test_gate_ignores_its_own_check_run(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = [
        {"name": "lint-workflows", "status": "completed", "conclusion": "success"},
        {"name": "merge-gate", "status": "completed", "conclusion": "failure"},
    ]
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, runs))
    assert exit_request is None
    assert any("push origin HEAD:refs/heads/dev" in command for command in bash_log.commands)


def test_gate_ignores_its_own_check_run_in_reusable_caller_spelling(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = [
        {"name": "preflight / preflight", "status": "completed", "conclusion": "success"},
        {"name": "merge-gate / merge-gate", "status": "in_progress", "conclusion": None},
    ]
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, runs))
    assert exit_request is None
    assert any("push origin HEAD:refs/heads/dev" in command for command in bash_log.commands)


def test_gate_normalizes_check_run_value_case(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = [{"name": "lint-workflows", "status": "completed", "conclusion": "SUCCESS"}]
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, runs))
    assert exit_request is None
    assert any("push origin HEAD:refs/heads/dev" in command for command in bash_log.commands)


def test_gate_refuses_incomplete_check_runs_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    responses[f"gh api repos/owner/repo/commits/{HEAD_SHA}/check-runs --paginate --slurp"] = json.dumps([
        {"total_count": 2, "check_runs": list(GREEN_RUNS)}
    ])
    exit_request, bash_log = run_gate(monkeypatch, responses)
    assert exit_request is not None
    assert "pagination incomplete" in exit_message(exit_request)
    assert not any("push" in command for command in bash_log.commands)


def test_gate_flattens_multi_page_check_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = [
        {"name": "lint-workflows", "status": "completed", "conclusion": "success"},
        {"name": "preflight / preflight", "status": "completed", "conclusion": "success"},
    ]
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), runs)
    responses[f"gh api repos/owner/repo/commits/{HEAD_SHA}/check-runs --paginate --slurp"] = json.dumps([
        {"total_count": 2, "check_runs": runs[:1]},
        {"total_count": 2, "check_runs": runs[1:]},
    ])
    exit_request, bash_log = run_gate(monkeypatch, responses)
    assert exit_request is None
    assert any("push origin HEAD:refs/heads/dev" in command for command in bash_log.commands)


def test_gate_refuses_when_no_open_pr_matches_the_head(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    responses["gh pr list --head feature-x --base dev --json number,headRefOid"] = json.dumps([
        {"number": 7, "headRefOid": "b" * 40}
    ])
    exit_request, _ = run_gate(monkeypatch, responses)
    assert exit_request is not None
    assert "none" in exit_message(exit_request)


def test_gate_refuses_ambiguous_pr_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    responses[f"git branch -r --contains {HEAD_SHA}"] = "  origin/feature-x\n  origin/feature-y\n"
    responses["gh pr list --head feature-y --base dev --json number,headRefOid"] = json.dumps([
        {"number": 9, "headRefOid": HEAD_SHA}
    ])
    exit_request, _ = run_gate(monkeypatch, responses)
    assert exit_request is not None
    assert "7, 9" in exit_message(exit_request)


def reject_ls_remote(command: str) -> bool:
    return "ls-remote" not in command


def reject_merge_base(command: str) -> bool:
    return "merge-base" not in command


def test_gate_refuses_when_checkout_is_not_the_pr_head(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    responses["git rev-parse HEAD"] = "b" * 40 + "\n"
    exit_request, bash_log = run_gate(monkeypatch, responses)
    assert exit_request is not None
    assert "is not the PR head" in exit_message(exit_request)
    assert not any("push" in command for command in bash_log.commands)


def test_gate_refuses_a_pr_not_rebased_onto_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    exit_request, bash_log = run_gate(monkeypatch, responses, bash_check_fn=reject_merge_base)
    assert exit_request is not None
    assert "rebase the PR onto dev" in exit_message(exit_request)
    assert not any("push origin HEAD:refs/heads/dev" in command for command in bash_log.commands)


def test_gate_deletes_merged_branch_after_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS))
    assert exit_request is None
    assert any("push origin --delete feature-x" in command for command in bash_log.commands)


def test_gate_skips_branch_deletion_when_head_is_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    responses["gh pr view 7 --json headRefName --jq .headRefName"] = "dev\n"
    exit_request, bash_log = run_gate(monkeypatch, responses)
    assert exit_request is None
    assert not any("--delete" in command for command in bash_log.commands)


def test_gate_skips_branch_deletion_when_head_is_main(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    responses["gh pr view 7 --json headRefName --jq .headRefName"] = "main\n"
    exit_request, bash_log = run_gate(monkeypatch, responses)
    assert exit_request is None
    assert not any("--delete" in command for command in bash_log.commands)


def test_gate_tolerates_already_deleted_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS), bash_check_fn=reject_ls_remote)
    assert exit_request is None
    assert not any("push origin --delete" in command for command in bash_log.commands)


def test_gate_sweeps_pr_releases_after_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    swept: list[tuple[str, str]] = []

    def record_sweep(prefix: str, repo: str) -> None:
        swept.append((prefix, repo))

    exit_request, _ = run_gate(
        monkeypatch,
        gate_responses(payload, GREEN_RUNS),
        delete_sweep_fn=record_sweep,
    )

    assert exit_request is None
    assert swept == [("pr-7-", "owner/repo")]


def test_gate_promotes_cache_tags_after_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    promoted: list[tuple[str, str, int]] = []

    def record_promote(registry: str, name: str, pr_number: int) -> list[str]:
        promoted.append((registry, name, pr_number))
        return ["capturetool-AndroidMobile-dev"]

    exit_request, _ = run_gate(
        monkeypatch,
        gate_responses(payload, GREEN_RUNS),
        promote_fn=record_promote,
    )

    assert exit_request is None
    assert promoted == [("ghcr.io/owner/repo/cache", "unity-library", 7)]


def test_gate_tolerates_a_failed_cache_promotion(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])

    def failing_promote(registry: str, name: str, pr_number: int) -> list[str]:
        raise CalledProcessError(returncode=1, cmd="oras repo tags ghcr.io/owner/repo/cache/unity-library")

    exit_request, _ = run_gate(
        monkeypatch,
        gate_responses(payload, GREEN_RUNS),
        promote_fn=failing_promote,
    )

    assert exit_request is None


def test_dry_run_reports_a_landed_shape_pr_without_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS), dry_run=True)
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)
    assert not any("merge --no-ff" in command for command in bash_log.commands)
    assert not any("--delete" in command for command in bash_log.commands)
    assert any("fetch origin refs/heads/dev" in command for command in bash_log.commands)


def test_dry_run_reports_the_cache_promotion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, _ = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS), dry_run=True)
    assert exit_request is None
    assert "would promote unity-library cache tags for pr-7" in capsys.readouterr().out


def test_dry_run_treats_a_missing_label_as_informational(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload([]), GREEN_RUNS)
    exit_request, bash_log = run_gate(monkeypatch, responses, dry_run=True)
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)


def test_dry_run_treats_a_closed_pr_as_informational(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"], state="CLOSED")
    exit_request, _ = run_gate(monkeypatch, gate_responses(payload, GREEN_RUNS), dry_run=True)
    assert exit_request is None


def test_dry_run_treats_red_checks_as_informational(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = [{"name": "lint-workflows", "status": "completed", "conclusion": "failure"}]
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(monkeypatch, gate_responses(payload, runs), dry_run=True)
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)


def test_dry_run_treats_a_missing_pr_match_as_informational(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    responses["gh pr list --head feature-x --base dev --json number,headRefOid"] = json.dumps([
        {"number": 7, "headRefOid": "b" * 40}
    ])
    exit_request, bash_log = run_gate(monkeypatch, responses, dry_run=True)
    assert exit_request is None
    assert not any("fetch origin" in command for command in bash_log.commands)


def test_dry_run_treats_a_non_rebased_pr_as_informational(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_gate(
        monkeypatch, gate_responses(payload, GREEN_RUNS), bash_check_fn=reject_merge_base, dry_run=True
    )
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)


def test_dry_run_treats_a_head_mismatch_as_informational(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = gate_responses(pr_view_payload(["ready-to-merge"]), GREEN_RUNS)
    responses["git rev-parse HEAD"] = "b" * 40 + "\n"
    exit_request, _ = run_gate(monkeypatch, responses, dry_run=True)
    assert exit_request is None
