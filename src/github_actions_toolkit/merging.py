from __future__ import annotations

import os
import re

from bashrun.bash import bash_check, bash_output
from pydantic import BaseModel, ConfigDict, Field

BASE_BRANCH = "dev"

# Answer git's credential prompt with the ambient GITHUB_TOKEN on every invocation
GIT_CREDENTIAL_HELPER = r"!f() { echo username=x-access-token; echo password=$GITHUB_TOKEN; }; f"
GIT_COMMAND = f"git -c credential.helper='{GIT_CREDENTIAL_HELPER}'"
FETCH_DEV_COMMAND = f"{GIT_COMMAND} fetch origin refs/heads/{BASE_BRANCH}"
PULL_REQUEST_REF_PATTERNS = (r"^refs/pull/(\d+)/merge$",)

AS_IS_INTEGRATE_LABEL = "approved-for-integrate"
REBASE_INTEGRATE_LABEL = "approved-for-rebase-integrate"
MERGE_LABEL = "approved-for-merge"
WRITE_PERMISSIONS = frozenset({"admin", "maintain", "write"})
NO_PERMISSION = "none"
PR_VIEW_FIELDS = "state,title,author,headRefOid,headRefName,baseRefName,labels,isDraft"


class LabelEntry(BaseModel):
    name: str


class ActorEntry(BaseModel):
    login: str


class PullRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    state: str
    title: str
    author: ActorEntry
    head_oid: str = Field(alias="headRefOid")
    head_ref_name: str = Field(alias="headRefName")
    base_ref_name: str = Field(alias="baseRefName")
    labels: list[LabelEntry]
    is_draft: bool = Field(alias="isDraft")


class PermissionEntry(BaseModel):
    permission: str


def pull_request_number_from_ref(ref: str) -> int:
    for pattern in PULL_REQUEST_REF_PATTERNS:
        if match := re.fullmatch(pattern, ref):
            return int(match.group(1))
    raise SystemExit(f"GITHUB_REF '{ref}' carries no PR number. Expected refs/pull/{{N}}/merge")


def candidate_ref(pr_number: int) -> str:
    return f"refs/heads/candidate/{pr_number}"


def tested_tag(pr_number: int) -> str:
    return f"tested/{pr_number}"


def view_pull_request(pr_number: int) -> PullRequest:
    return PullRequest.model_validate_json(bash_output(f"gh pr view {pr_number} --json {PR_VIEW_FIELDS}"))


def label_names(pull_request: PullRequest) -> set[str]:
    return {label.name for label in pull_request.labels}


def author_permission(author: str) -> str:
    command = f"gh api repos/{os.environ['GITHUB_REPOSITORY']}/collaborators/{author}/permission"

    # Treat a failed lookup as none, because a stranger is not a collaborator
    if not bash_check(command):
        return NO_PERMISSION
    return PermissionEntry.model_validate_json(bash_output(command)).permission
