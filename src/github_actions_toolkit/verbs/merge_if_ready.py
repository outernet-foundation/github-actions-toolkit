from __future__ import annotations

from subprocess import CalledProcessError
from typing import Annotated

import typer
from bashrun.bash import bash, bash_check, bash_output
from build_artifact_registry.cache import promote_scope
from build_artifact_registry.setup_oras import install_oras

from github_actions_toolkit.config import Settings
from github_actions_toolkit.merging import (
    AS_IS_INTEGRATE_LABEL,
    BASE_BRANCH,
    FETCH_DEV_COMMAND,
    GIT_COMMAND,
    MERGE_LABEL,
    PullRequest,
    candidate_ref,
    label_names,
    pull_request_number_from_ref,
    tested_tag,
    view_pull_request,
)
from github_actions_toolkit.releases import delete_releases_by_prefix

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

MAX_ATTEMPTS = 3
RE_POKE_MESSAGE = f"Re-apply the {MERGE_LABEL} label to restart the merge"
SCOPE_PROMOTED_CACHE_REPOSITORIES = ["unity-library"]


@app.command()
def main(
    dry_run: Annotated[
        bool, typer.Option(help="Exercise the full machinery and report, with zero side effects")
    ] = False,
) -> None:
    settings = Settings.model_validate({})
    repository = settings.github_repository
    pr_number = pull_request_number_from_ref(settings.github_ref)
    pr_head_sha = settings.pr_head_sha
    attempt = settings.github_run_attempt
    if not pr_head_sha:
        raise SystemExit("PR_HEAD_SHA is not set")
    if not attempt:
        raise SystemExit("GITHUB_RUN_ATTEMPT is not set")

    pull_request = view_pull_request(pr_number)

    if pull_request.state != "OPEN":
        print(f"  PR #{pr_number} is {pull_request.state}, not OPEN")
        return

    # Stamp the tested marker, because the terminal only runs post-green and the candidate at HEAD is certified against its dev tip
    stamp_tested_marker(pr_number, dry_run)

    if pull_request.is_draft:
        print(f"  PR #{pr_number} is a draft, marking it ready for review re-enters the loop")
        return

    if MERGE_LABEL not in label_names(pull_request):
        print(f"  the {MERGE_LABEL} label is not on PR #{pr_number}")
        return

    # If the as-is label raced in mid-run
    if AS_IS_INTEGRATE_LABEL in label_names(pull_request):
        abort(
            f"PR #{pr_number} carries {AS_IS_INTEGRATE_LABEL}: an as-is branch never merges."
            f" Remove it to merge. {RE_POKE_MESSAGE}",
            dry_run,
        )
        return

    # If commits were pushed since the run began
    if head_moved(pull_request, pr_head_sha):
        abort(f"the PR #{pr_number} head moved while the run ran. {RE_POKE_MESSAGE}", dry_run)
        return

    moved = dev_moved()
    # If the base branch moved since the gate job rebased onto it
    if moved and int(attempt) > MAX_ATTEMPTS:
        abort(f"{BASE_BRANCH} moved more than {MAX_ATTEMPTS} times while the run ran. {RE_POKE_MESSAGE}", dry_run)
        return
    if moved and dry_run:
        print(f"  would dispatch a retry of this run (attempt {int(attempt) + 1})")
        return
    if moved:
        # Retry the integrate run
        bash(
            f"gh workflow run {settings.retry_workflow} --repo {repository}"
            f" --ref {BASE_BRANCH} -f run-id={settings.github_run_id}"
        )
        print(f"  {BASE_BRANCH} moved. Dispatched a retry of run {settings.github_run_id}")
        return

    if dry_run:
        print(f"  would merge PR #{pr_number} through the rebase-merge API under lease {pr_head_sha[:12]}")
        return

    # Tag the tested tree because the merge replay below mints new SHAs
    candidate_oid = bash_output("git rev-parse HEAD").strip()
    tag = f"certified/{pr_number}"
    bash(f"git tag -f {tag} {candidate_oid}")
    bash(f"{GIT_COMMAND} push --force origin refs/tags/{tag}")
    print(
        f"  tagged the certified candidate {candidate_oid[:12]} as refs/tags/{tag}: the merge replays it"
        f" as new SHAs, so this tag is the only durable pointer to the tested tree"
    )

    # Rebase and merge using the github api
    try:
        bash(f"gh api -X PUT repos/{repository}/pulls/{pr_number}/merge -f merge_method=rebase -f sha={pr_head_sha}")
    except CalledProcessError as failure:
        # Determine the failure by re-reading the state, because gh hides the HTTP status (cli/cli#10579)

        # If the head moved while the run ran
        if head_moved(view_pull_request(pr_number), pr_head_sha):
            raise SystemExit(
                f"the merge API refused: the PR #{pr_number} head moved while the run ran. {RE_POKE_MESSAGE}"
            ) from failure

        # If dev moved while the run ran
        if dev_moved():
            raise SystemExit(
                f"the merge API refused: {BASE_BRANCH} moved while the run ran. {RE_POKE_MESSAGE}"
            ) from failure

        # Treat any other refusal as unexpected
        raise SystemExit(f"the merge API refused to merge PR #{pr_number} in an unexpected way: {failure}") from failure

    print(f"  merged PR #{pr_number} into {BASE_BRANCH} through the rebase-merge API")

    bash(FETCH_DEV_COMMAND)

    # If the merged dev tree differs from the tagged candidate
    if not bash_check(f"git diff --quiet {candidate_oid} FETCH_HEAD"):
        raise SystemExit(
            f"CATASTROPHIC ERROR: the merged {BASE_BRANCH} tree differs from the certified candidate {candidate_oid[:12]}"
            ": the evergreen invariant was violated, revert or retest dev immediately"
        )

    print(f"  verified the merged {BASE_BRANCH} tree matches the certified candidate {candidate_oid[:12]}")

    # Delete the rebased branch we used for the integrate run
    candidate_branch = candidate_ref(pr_number)
    bash(f"{GIT_COMMAND} push origin --delete {candidate_branch}")
    print(f"  deleted {candidate_branch}")

    # Consume the marker with the merge and let the closed-PR sweep backstop interrupted ones
    tested = tested_tag(pr_number)
    bash(f"{GIT_COMMAND} push origin --delete refs/tags/{tested}")
    print(f"  deleted refs/tags/{tested}")

    # If the PR head branch exists and is neither dev nor main
    if pull_request.head_ref_name not in (BASE_BRANCH, "main") and bash_check(
        f"{GIT_COMMAND} ls-remote --heads origin {pull_request.head_ref_name}"
    ):
        bash(f"{GIT_COMMAND} push origin --delete {pull_request.head_ref_name}")
        print(f"  deleted branch {pull_request.head_ref_name}")

    # Delete the PR's per-run build releases
    delete_releases_by_prefix(f"pr-{pr_number}-", repository)

    # Promote the PR's build caches onto the dev scope best-effort, because a failure never fails the merge
    registry = f"ghcr.io/{repository}/cache"
    try:
        install_oras()
    except CalledProcessError as failure:
        print(f"WARNING: provisioning oras failed for PR #{pr_number}, cache promotion skipped ({failure})")
    else:
        for cache_name in SCOPE_PROMOTED_CACHE_REPOSITORIES:
            try:
                promoted = promote_scope(registry, cache_name, pr_number)
            except CalledProcessError as failure:
                print(
                    f"WARNING: promoting {cache_name} onto the dev scope failed for PR #{pr_number}"
                    f", the dev cache is not refreshed and the next PR falls back to the previous one ({failure})"
                )
            else:
                if promoted:
                    print(f"  promoted {len(promoted)} {cache_name} tag(s) onto the dev scope")


def stamp_tested_marker(pr_number: int, dry_run: bool) -> None:
    tag = tested_tag(pr_number)
    if dry_run:
        print(f"  would stamp the tested marker refs/tags/{tag} at the certified candidate")
        return
    candidate_oid = bash_output("git rev-parse HEAD").strip()
    bash(f"git tag -f {tag} {candidate_oid}")
    bash(f"{GIT_COMMAND} push --force origin refs/tags/{tag}")
    print(f"  stamped refs/tags/{tag} at candidate {candidate_oid[:12]}")


def abort(reason: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  would abort: {reason}")
        return
    raise SystemExit(reason)


def head_moved(pull_request: PullRequest, lease: str) -> bool:
    return pull_request.head_oid != lease


def dev_moved() -> bool:
    bash(FETCH_DEV_COMMAND)
    return not bash_check("git merge-base --is-ancestor FETCH_HEAD HEAD")
