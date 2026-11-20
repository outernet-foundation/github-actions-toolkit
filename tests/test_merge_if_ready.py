import json
from collections.abc import Callable
from subprocess import CalledProcessError

import pytest

from github_actions_toolkit import pull_requests as pull_requests_module
from github_actions_toolkit.pull_requests import PR_VIEW_FIELDS
from github_actions_toolkit.verbs import merge_if_ready

PAYLOAD_SHA = "a" * 40
CANDIDATE_SHA = "b" * 40
CANDIDATE_REF = "refs/heads/candidate/7"
RUN_ID = "4242"


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
    def __init__(self, refuse_fragment: str = "") -> None:
        self.commands: list[str] = []
        self.refuse_fragment = refuse_fragment

    def __call__(self, command: str, **kwargs: object) -> None:
        self.commands.append(command)
        if self.refuse_fragment and self.refuse_fragment in command:
            raise CalledProcessError(returncode=1, cmd=command, output="", stderr="Method Not Available")


def pr_view_payload(
    labels: list[str],
    state: str = "OPEN",
    title: str = "Test PR",
    is_draft: bool = False,
) -> str:
    return json.dumps({
        "state": state,
        "title": title,
        "headRefOid": PAYLOAD_SHA,
        "headRefName": "feature-x",
        "baseRefName": "dev",
        "labels": [{"name": name} for name in labels],
        "isDraft": is_draft,
    })


def moved_pr_view_payload(payload: str, head_oid: str) -> str:
    document = json.loads(payload)
    document["headRefOid"] = head_oid
    return json.dumps(document)


def merge_responses(payload: str) -> dict[str, str]:
    return {
        f"gh pr view 7 --json {PR_VIEW_FIELDS}": payload,
        "git rev-parse HEAD": f"{CANDIDATE_SHA}\n",
    }


def accept_any_bash_check(command: str) -> bool:
    return True


def reject_merge_base(command: str) -> bool:
    return "merge-base" not in command


class AncestorOnceThenMoved:
    def __init__(self) -> None:
        self.merge_base_calls = 0

    def __call__(self, command: str) -> bool:
        if "merge-base" not in command:
            return True
        first = self.merge_base_calls == 0
        self.merge_base_calls += 1
        return first


def refuse_only_the_merged_diff(command: str) -> bool:
    return not command.startswith("git diff --quiet")


def noop_sweep(prefix: str, repo: str) -> None:
    pass


def noop_install_oras() -> None:
    pass


def noop_promote(registry: str, name: str, pr_number: int) -> list[str]:
    return []


def exit_message(exit_request: SystemExit) -> str:
    return str(exit_request.code)


def patch_merge(
    monkeypatch: pytest.MonkeyPatch,
    bash_function: object,
    responses: object,
    bash_check_fn: Callable[[str], bool] | None = None,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("GITHUB_RUN_ID", RUN_ID)
    monkeypatch.setenv("PR_HEAD_SHA", PAYLOAD_SHA)
    monkeypatch.setattr(merge_if_ready, "bash_output", responses)
    monkeypatch.setattr(pull_requests_module, "bash_output", responses)
    monkeypatch.setattr(merge_if_ready, "bash", bash_function)
    monkeypatch.setattr(merge_if_ready, "bash_check", bash_check_fn or accept_any_bash_check)
    monkeypatch.setattr(merge_if_ready, "delete_releases_by_prefix", noop_sweep)
    monkeypatch.setattr(merge_if_ready, "install_oras", noop_install_oras)
    monkeypatch.setattr(merge_if_ready, "promote_scope", noop_promote)


def run_merge(
    monkeypatch: pytest.MonkeyPatch,
    responses: object,
    attempt: str = "1",
    bash_check_fn: Callable[[str], bool] | None = None,
    dry_run: bool = False,
    refuse_fragment: str = "",
) -> tuple[SystemExit | None, BashLog]:
    bash_log = BashLog(refuse_fragment=refuse_fragment)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", attempt)
    patch_merge(monkeypatch, bash_log, responses, bash_check_fn)
    try:
        merge_if_ready.main(dry_run=dry_run)
    except SystemExit as exit_request:
        return exit_request, bash_log
    return None, bash_log


def test_merge_requires_the_pr_head_sha_env(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    bash_log = BashLog()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.delenv("PR_HEAD_SHA", raising=False)
    monkeypatch.setattr(merge_if_ready, "bash_output", CommandResponses(merge_responses(payload)))
    monkeypatch.setattr(merge_if_ready, "bash", bash_log)
    exit_request = None
    try:
        merge_if_ready.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is not None
    assert "PR_HEAD_SHA" in exit_message(exit_request)


def test_merge_requires_the_run_attempt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    bash_log = BashLog()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("PR_HEAD_SHA", PAYLOAD_SHA)
    monkeypatch.delenv("GITHUB_RUN_ATTEMPT", raising=False)
    monkeypatch.setattr(merge_if_ready, "bash_output", CommandResponses(merge_responses(payload)))
    monkeypatch.setattr(merge_if_ready, "bash", bash_log)
    exit_request = None
    try:
        merge_if_ready.main(dry_run=False)
    except SystemExit as request:
        exit_request = request
    assert exit_request is not None
    assert "GITHUB_RUN_ATTEMPT" in exit_message(exit_request)


def test_merge_quietly_skips_a_pr_not_open(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"], state="MERGED")
    exit_request, bash_log = run_merge(monkeypatch, CommandResponses(merge_responses(payload)))
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)


def test_merge_quietly_skips_when_the_label_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload([])
    exit_request, bash_log = run_merge(monkeypatch, CommandResponses(merge_responses(payload)))
    assert exit_request is None
    assert any("push --force origin refs/tags/tested/7" in command for command in bash_log.commands)
    assert not any("certified" in command for command in bash_log.commands)
    assert not any("push origin --delete" in command for command in bash_log.commands)


def test_merge_quietly_skips_a_draft_even_when_labeled(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"], is_draft=True)
    exit_request, bash_log = run_merge(monkeypatch, CommandResponses(merge_responses(payload)))
    assert exit_request is None
    assert any("push --force origin refs/tags/tested/7" in command for command in bash_log.commands)
    assert not any("certified" in command for command in bash_log.commands)
    assert not any("pulls/7/merge" in command for command in bash_log.commands)


def test_merge_refuses_the_as_is_label_raced_in_mid_run(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge", "ready-to-integrate"])
    exit_request, bash_log = run_merge(monkeypatch, CommandResponses(merge_responses(payload)))
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "ready-to-integrate" in message
    assert "never merges" in message
    assert any("push --force origin refs/tags/tested/7" in command for command in bash_log.commands)
    assert not any("certified" in command for command in bash_log.commands)


def test_merge_aborts_when_the_pr_head_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    moved_sha = "d" * 40
    responses = merge_responses(payload)
    responses[f"gh pr view 7 --json {PR_VIEW_FIELDS}"] = moved_pr_view_payload(payload, moved_sha)
    exit_request, bash_log = run_merge(monkeypatch, CommandResponses(responses))
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "head moved while the run ran" in message
    assert "Re-apply the ready-to-merge label" in message
    assert any("push --force origin refs/tags/tested/7" in command for command in bash_log.commands)
    assert not any("certified" in command for command in bash_log.commands)
    assert not any("push origin --delete" in command for command in bash_log.commands)


def test_merge_dispatches_a_retry_when_dev_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_merge(
        monkeypatch, CommandResponses(merge_responses(payload)), attempt="1", bash_check_fn=reject_merge_base
    )
    assert exit_request is None
    assert any(
        f"gh workflow run retry.yml --repo owner/repo --ref dev -f run-id={RUN_ID}" in command
        for command in bash_log.commands
    )
    assert not any("git rebase" in command for command in bash_log.commands)
    assert not any("--force-with-lease" in command for command in bash_log.commands)
    assert not any("pulls/7/merge" in command for command in bash_log.commands)


def test_merge_dispatches_the_named_retry_shim(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    monkeypatch.setenv("RETRY_WORKFLOW", "_retry.yml")
    exit_request, bash_log = run_merge(
        monkeypatch, CommandResponses(merge_responses(payload)), bash_check_fn=reject_merge_base
    )
    assert exit_request is None
    assert any(
        f"gh workflow run _retry.yml --repo owner/repo --ref dev -f run-id={RUN_ID}" in command
        for command in bash_log.commands
    )


def test_merge_fails_loud_beyond_the_attempt_bound_without_dispatching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_merge(
        monkeypatch, CommandResponses(merge_responses(payload)), attempt="4", bash_check_fn=reject_merge_base
    )
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "moved more than 3 times" in message
    assert "Re-apply the ready-to-merge label" in message
    assert any("push --force origin refs/tags/tested/7" in command for command in bash_log.commands)
    assert not any("certified" in command for command in bash_log.commands)
    assert not any("push origin --delete" in command for command in bash_log.commands)
    assert not any("workflow run" in command for command in bash_log.commands)


def test_merge_merges_through_the_rebase_merge_api(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_merge(monkeypatch, CommandResponses(merge_responses(payload)))
    assert exit_request is None
    assert any(f"git tag -f certified/7 {CANDIDATE_SHA}" in command for command in bash_log.commands)
    assert any("push --force origin refs/tags/certified/7" in command for command in bash_log.commands)
    assert any("push --force origin refs/tags/tested/7" in command for command in bash_log.commands)
    assert any(
        f"gh api -X PUT repos/owner/repo/pulls/7/merge -f merge_method=rebase -f sha={PAYLOAD_SHA}" in command
        for command in bash_log.commands
    )
    assert any(f"push origin --delete {CANDIDATE_REF}" in command for command in bash_log.commands)
    assert any("push origin --delete refs/tags/tested/7" in command for command in bash_log.commands)
    assert any("push origin --delete feature-x" in command for command in bash_log.commands)
    assert not any("--force-with-lease" in command for command in bash_log.commands)
    assert not any("git merge" in command for command in bash_log.commands)
    assert not any("push origin HEAD:refs/heads/dev" in command for command in bash_log.commands)


def test_merge_sweeps_and_promotes_on_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    swept: list[tuple[str, str]] = []
    promoted: list[tuple[str, str, int]] = []

    def record_sweep(prefix: str, repo: str) -> None:
        swept.append((prefix, repo))

    def record_promote(registry: str, name: str, pr_number: int) -> list[str]:
        promoted.append((registry, name, pr_number))
        return ["capturetool-AndroidMobile-dev"]

    bash_log = BashLog()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("GITHUB_RUN_ID", RUN_ID)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("PR_HEAD_SHA", PAYLOAD_SHA)
    monkeypatch.setattr(merge_if_ready, "bash_output", CommandResponses(merge_responses(payload)))
    monkeypatch.setattr(pull_requests_module, "bash_output", CommandResponses(merge_responses(payload)))
    monkeypatch.setattr(merge_if_ready, "bash", bash_log)
    monkeypatch.setattr(merge_if_ready, "bash_check", accept_any_bash_check)
    monkeypatch.setattr(merge_if_ready, "bash_output", CommandResponses(merge_responses(payload)))
    monkeypatch.setattr(merge_if_ready, "bash", bash_log)
    monkeypatch.setattr(merge_if_ready, "bash_check", accept_any_bash_check)
    monkeypatch.setattr(merge_if_ready, "delete_releases_by_prefix", record_sweep)
    monkeypatch.setattr(merge_if_ready, "install_oras", noop_install_oras)
    monkeypatch.setattr(merge_if_ready, "promote_scope", record_promote)
    merge_if_ready.main()
    assert swept == [("pr-7-", "owner/repo")]
    assert promoted == [("ghcr.io/owner/repo/cache", "unity-library", 7)]


def test_merge_tolerates_a_failed_cache_promotion(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])

    def failing_promote(registry: str, name: str, pr_number: int) -> list[str]:
        raise CalledProcessError(returncode=1, cmd="oras repo tags ghcr.io/owner/repo/cache/unity-library")

    bash_log = BashLog()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("GITHUB_RUN_ID", RUN_ID)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("PR_HEAD_SHA", PAYLOAD_SHA)
    monkeypatch.setattr(merge_if_ready, "bash_output", CommandResponses(merge_responses(payload)))
    monkeypatch.setattr(pull_requests_module, "bash_output", CommandResponses(merge_responses(payload)))
    monkeypatch.setattr(merge_if_ready, "bash", bash_log)
    monkeypatch.setattr(merge_if_ready, "bash_check", accept_any_bash_check)
    monkeypatch.setattr(merge_if_ready, "bash_output", CommandResponses(merge_responses(payload)))
    monkeypatch.setattr(merge_if_ready, "bash", bash_log)
    monkeypatch.setattr(merge_if_ready, "bash_check", accept_any_bash_check)
    monkeypatch.setattr(merge_if_ready, "delete_releases_by_prefix", noop_sweep)
    monkeypatch.setattr(merge_if_ready, "install_oras", noop_install_oras)
    monkeypatch.setattr(merge_if_ready, "promote_scope", failing_promote)
    merge_if_ready.main()


def test_merge_maps_an_api_refusal_to_a_moved_pr_head(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    moved = moved_pr_view_payload(payload, "d" * 40)
    responses = SequencedResponses(
        merge_responses(payload),
        {f"gh pr view 7 --json {PR_VIEW_FIELDS}": [payload, moved]},
    )
    exit_request, _ = run_merge(monkeypatch, responses, refuse_fragment="pulls/7/merge")
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "the merge API refused" in message
    assert "head moved while the run ran" in message


def test_merge_maps_an_api_refusal_to_a_moved_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, _ = run_merge(
        monkeypatch,
        CommandResponses(merge_responses(payload)),
        bash_check_fn=AncestorOnceThenMoved(),
        refuse_fragment="pulls/7/merge",
    )
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "the merge API refused" in message
    assert "dev moved while the run ran" in message


def test_merge_fails_loud_on_an_unexplained_api_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, _ = run_merge(
        monkeypatch, CommandResponses(merge_responses(payload)), refuse_fragment="pulls/7/merge"
    )
    assert exit_request is not None
    message = exit_message(exit_request)
    assert "the merge API refused to merge PR #7" in message


def test_merge_alarms_when_the_merged_tree_differs_from_the_certified_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, _ = run_merge(
        monkeypatch, CommandResponses(merge_responses(payload)), bash_check_fn=refuse_only_the_merged_diff
    )
    assert exit_request is not None
    assert "evergreen invariant was violated" in exit_message(exit_request)


def test_merge_dry_run_names_the_stamp_and_the_merge(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_merge(monkeypatch, CommandResponses(merge_responses(payload)), dry_run=True)
    assert exit_request is None
    assert not any("push" in command for command in bash_log.commands)
    output = capsys.readouterr().out
    assert "would stamp the tested marker refs/tags/tested/7" in output
    assert "would merge PR #7 through the rebase-merge API under lease aaaaaaaaaaaa" in output


def test_merge_dry_run_names_the_retry_for_a_moved_dev(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = pr_view_payload(["ready-to-merge"])
    exit_request, bash_log = run_merge(
        monkeypatch, CommandResponses(merge_responses(payload)), bash_check_fn=reject_merge_base, dry_run=True
    )
    assert exit_request is None
    assert not any("workflow run" in command for command in bash_log.commands)
    assert "would dispatch a retry of this run (attempt 2)" in capsys.readouterr().out
