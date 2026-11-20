from __future__ import annotations

from bashrun.bash import bash_output
from pydantic import BaseModel, ConfigDict, Field

AS_IS_INTEGRATE_LABEL = "ready-to-integrate"
REBASE_INTEGRATE_LABEL = "ready-to-rebase-integrate"
MERGE_LABEL = "ready-to-merge"
PR_VIEW_FIELDS = "state,title,headRefOid,headRefName,baseRefName,labels,isDraft"


class LabelEntry(BaseModel):
    name: str


class PullRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    state: str
    title: str
    head_oid: str = Field(alias="headRefOid")
    head_ref_name: str = Field(alias="headRefName")
    base_ref_name: str = Field(alias="baseRefName")
    labels: list[LabelEntry]
    is_draft: bool = Field(alias="isDraft")


def view_pull_request(pr_number: int) -> PullRequest:
    return PullRequest.model_validate_json(bash_output(f"gh pr view {pr_number} --json {PR_VIEW_FIELDS}"))


def label_names(pull_request: PullRequest) -> set[str]:
    return {label.name for label in pull_request.labels}
