from __future__ import annotations

import json

from bashrun.bash import bash, bash_output


def delete_releases_by_prefix(prefix: str, repository: str) -> None:
    releases = json.loads(bash_output(f"gh release list --repo {repository} --json tagName"))
    for release in releases:
        tag_name = release["tagName"]
        if tag_name.startswith(prefix):
            bash(f"gh release delete {tag_name} --cleanup-tag --yes --repo {repository}")
