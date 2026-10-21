from __future__ import annotations

import json
import re

from bashrun.bash import bash, bash_output

PR_RELEASE_TAG_PATTERN = re.compile(r"^pr-(\d+)-(\d+)$")


def delete_releases_by_prefix(prefix: str, repository: str) -> None:
    releases = json.loads(bash_output(f"gh release list --repo {repository} --json tagName"))
    for release in releases:
        tag_name = release["tagName"]
        if tag_name.startswith(prefix):
            bash(f"gh release delete {tag_name} --cleanup-tag --yes --repo {repository}")


def sweep_superseded_pr_releases(tag: str, repository: str) -> None:
    current = PR_RELEASE_TAG_PATTERN.fullmatch(tag)
    if current is None:
        raise ValueError(f"tag '{tag}' is not a per-run PR release tag")
    pr_number, keep_count = int(current.group(1)), int(current.group(2))
    releases = json.loads(bash_output(f"gh release list --repo {repository} --json tagName"))
    for release in releases:
        candidate = PR_RELEASE_TAG_PATTERN.fullmatch(release["tagName"])
        # Only lower counts go, so a late-finishing older run never deletes a newer run's release
        if candidate and int(candidate.group(1)) == pr_number and int(candidate.group(2)) < keep_count:
            bash(f"gh release delete {release['tagName']} --cleanup-tag --yes --repo {repository}")
