from __future__ import annotations

import re

BASE_BRANCH = "dev"

# Answer git's credential prompt with the ambient GITHUB_TOKEN on every invocation
GIT_CREDENTIAL_HELPER = r"!f() { echo username=x-access-token; echo password=$GITHUB_TOKEN; }; f"
GIT_COMMAND = f"git -c credential.helper='{GIT_CREDENTIAL_HELPER}'"
FETCH_DEV_COMMAND = f"{GIT_COMMAND} fetch origin refs/heads/{BASE_BRANCH}"
PULL_REQUEST_REF_PATTERNS = (r"^refs/pull/(\d+)/merge$",)


def pull_request_number_from_ref(ref: str) -> int:
    for pattern in PULL_REQUEST_REF_PATTERNS:
        if match := re.fullmatch(pattern, ref):
            return int(match.group(1))
    raise SystemExit(f"GITHUB_REF '{ref}' carries no PR number. Expected refs/pull/{{N}}/merge")


def candidate_ref(pr_number: int) -> str:
    return f"refs/heads/candidate/{pr_number}"
