from __future__ import annotations

import json
from pathlib import Path

import pytest

from github_actions_toolkit import plan as plan_module
from github_actions_toolkit.config import AppConfig, BuildArtifactConfig, PublishConfig
from github_actions_toolkit.plan import ReleasePlan
from github_actions_toolkit.verbs import release as release_module
from github_actions_toolkit.verbs.release import (
    DIGEST_FILE_NAME,
    DigestEntry,
    ReleaseChannel,
    delete_draft_release,
)

DRAFT_URL = "https://github.com/owner/repo/releases/untagged-abc"
DRAFT_VIEW_JSON = json.dumps({"body": "", "url": DRAFT_URL})
DRAFT_REPOSITORY = "owner/repo"
CERTIFIED_SHA = "abcdef1234567890abcdef1234567890abcdef12"
SHORT_SHA = CERTIFIED_SHA[:12]
COMMIT_COUNT = 1563


class BashLog:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def __call__(self, command: str) -> None:
        self.commands.append(command)


class FixedReturn:
    def __init__(self, value: object) -> None:
        self.value = value

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self.value


class FakeTags:
    def __init__(self, versions: dict[str, str | None], changed: set[str]) -> None:
        self._versions = versions
        self._changed = changed

    def latest_version(self, prefix: str) -> str | None:
        return self._versions.get(prefix.removesuffix("-v"))

    def has_changes_since(self, tag: str | None, path: Path) -> bool:
        if tag is None:
            return True
        return tag.rsplit("-v", 1)[0] in self._changed


class FakePullArtifact:
    def __init__(self, layers: dict[tuple[str, ...], dict[str, str]]) -> None:
        self.layers = layers
        self.calls: list[tuple[object, ...]] = []

    def __call__(
        self,
        builds_registry: str,
        project: str,
        platform: str,
        tag: str,
        target: Path,
        **kwargs: object,
    ) -> bool:
        self.calls.append((builds_registry, project, platform, tag, target))
        files = self.layers.get((project, platform, tag), self.layers.get((project, platform)))
        if files is None:
            return False
        target.mkdir(parents=True, exist_ok=True)
        for file_name, content in files.items():
            (target / file_name).write_text(content, encoding="utf-8")
        return True


def digest_layer(manifest: dict[str, DigestEntry]) -> dict[tuple[str, str], dict[str, str]]:
    data = {name: entry.model_dump() for name, entry in manifest.items()}
    return {("images-digests", "all"): {DIGEST_FILE_NAME: json.dumps(data)}}


def patch_plan_tags(monkeypatch: pytest.MonkeyPatch, tags: FakeTags) -> None:
    monkeypatch.setattr(plan_module, "get_latest_version", tags.latest_version)
    monkeypatch.setattr(plan_module, "has_changes_since", tags.has_changes_since)
    monkeypatch.setattr(release_module, "get_latest_version", tags.latest_version)


def make_build_config() -> PublishConfig:
    return PublishConfig(
        apps={
            "myapp": AppConfig(
                path=Path("apps/myapp"),
                major_minor="1.0",
                builds=[BuildArtifactConfig(project="MyApp", platform="AndroidMobile", file="MyApp-AndroidMobile.apk")],
            )
        },
    )


def patch_image_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "workloads" / "images.yml"
    manifest.parent.mkdir()
    manifest.write_text("services: {}\n", encoding="utf-8")


def patch_context(
    monkeypatch: pytest.MonkeyPatch,
    publish_config: PublishConfig,
    github_ref: str = "refs/pull/107/merge",
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", DRAFT_REPOSITORY)
    monkeypatch.setenv("GITHUB_ACTOR", "bot")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")
    monkeypatch.setenv("GITHUB_REF", github_ref)
    monkeypatch.setattr(release_module, "load_config", FixedReturn(publish_config))
    monkeypatch.setattr(release_module, "compute_release_plan", FixedReturn(ReleasePlan.empty()))


def patch_bash(monkeypatch: pytest.MonkeyPatch, check_returns: object = False) -> BashLog:
    monkeypatch.setattr(release_module, "bash_check", FixedReturn(check_returns))
    bash_log = BashLog()
    monkeypatch.setattr(release_module, "bash", bash_log)
    return bash_log


def patch_pr_bash_output(monkeypatch: pytest.MonkeyPatch, body: str = "", api_versions: str = "[]") -> None:
    def dispatching_bash_output(command: str) -> str:
        if command == "git rev-parse HEAD":
            return CERTIFIED_SHA
        if command == f"git rev-list --count {CERTIFIED_SHA}":
            return str(COMMIT_COUNT)
        if command.startswith("gh api /orgs/"):
            return api_versions
        return json.dumps({"body": body})

    monkeypatch.setattr(release_module, "bash_output", dispatching_bash_output)


def patch_pull_artifact(
    monkeypatch: pytest.MonkeyPatch, layers: dict[tuple[str, ...], dict[str, str]]
) -> FakePullArtifact:
    pull_artifact = FakePullArtifact(layers)
    monkeypatch.setattr(release_module, "pull_artifact", pull_artifact)
    monkeypatch.setattr(release_module, "list_build_tags", FixedReturn([]))
    return pull_artifact


def shard_layer(tag: str, manifest: dict[str, DigestEntry]) -> dict[tuple[str, str, str], dict[str, str]]:
    data = {name: entry.model_dump() for name, entry in manifest.items()}
    return {("images-digests", "all", tag): {DIGEST_FILE_NAME: json.dumps(data)}}


def capturing_bash(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    written: list[str] = []

    def capturing(command: str) -> None:
        if "--notes-file" in command:
            path = command.split("--notes-file", 1)[1].strip().split()[0]
            written.append(Path(path).read_text(encoding="utf-8"))

    monkeypatch.setattr(release_module, "bash", capturing)
    return written


def test_delete_draft_release_deletes_without_cleanup_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    bash_log = patch_bash(monkeypatch, check_returns=True)

    delete_draft_release("pr-7", "owner/repo")

    assert any(
        "gh release delete pr-7" in command and "--cleanup-tag" not in command and "--yes" in command
        for command in bash_log.commands
    )


def test_delete_draft_release_noop_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    bash_log = patch_bash(monkeypatch, check_returns=False)

    delete_draft_release("pr-7", "owner/repo")

    assert not bash_log.commands


def test_update_pr_draft_derives_pr_tag_and_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_context(monkeypatch, make_build_config())
    patch_plan_tags(monkeypatch, FakeTags(versions={"myapp": "1.0.0"}, changed={"myapp"}))
    patch_pull_artifact(monkeypatch, {("MyApp", "AndroidMobile"): {"MyApp.apk": "build content"}})
    patch_pr_bash_output(monkeypatch)
    bash_log = patch_bash(monkeypatch, check_returns=False)

    release_module.main(channel=ReleaseChannel.PR)

    assert any("pr-107" in command for command in bash_log.commands)
    assert any("gh release upload pr-107" in command and "--clobber" in command for command in bash_log.commands)
    assert any(f"MyApp-AndroidMobile-{COMMIT_COUNT}.apk" in command for command in bash_log.commands)
    assert any("gh release edit pr-107" in command and "--notes-file" in command for command in bash_log.commands)


def test_update_pr_draft_writes_image_section_when_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = {"zed-capture": DigestEntry(ref="ghcr.io/owner/repo/zed-capture", digest="sha256:abc", tags=["tree-1"])}
    patch_image_manifest(monkeypatch, tmp_path)
    patch_context(monkeypatch, make_build_config())
    patch_pull_artifact(
        monkeypatch, {("MyApp", "AndroidMobile"): {"MyApp.apk": "build content"}, **digest_layer(manifest)}
    )
    patch_plan_tags(monkeypatch, FakeTags(versions={"myapp": "1.0.0"}, changed={"myapp"}))
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)
    written = capturing_bash(monkeypatch)

    release_module.main(channel=ReleaseChannel.PR)

    assert written
    assert "| Image | Tag |" in written[0]
    assert "| zed-capture | [`tree-1`](https://github.com/owner/repo/pkgs/container/repo%2Fzed-capture) |" in written[0]
    assert "sha256:abc" not in written[0]
    assert f"### Commit [{SHORT_SHA}](https://github.com/owner/repo/commit/{CERTIFIED_SHA})" in written[0]
    assert f"sha-{SHORT_SHA}" in written[0]


def test_update_pr_draft_links_image_tag_to_exact_package_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = {"zed-capture": DigestEntry(ref="ghcr.io/owner/repo/zed-capture", digest="sha256:abc", tags=["tree-1"])}
    api_versions = json.dumps([{"name": "sha256:zzz", "id": 1}, {"name": "sha256:abc", "id": 1369985695}])
    patch_image_manifest(monkeypatch, tmp_path)
    patch_context(monkeypatch, PublishConfig())
    patch_pull_artifact(monkeypatch, digest_layer(manifest))
    patch_pr_bash_output(monkeypatch, api_versions=api_versions)
    patch_bash(monkeypatch, check_returns=False)
    written = capturing_bash(monkeypatch)

    release_module.main(channel=ReleaseChannel.PR)

    assert written
    assert (
        "| zed-capture | [`tree-1`](https://github.com/owner/repo/pkgs/container/repo%2Fzed-capture/1369985695"
        "?tag=tree-1) |" in written[0]
    )


def test_update_pr_draft_lists_images_alphabetically_by_ref(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = {
        "zed-capture": DigestEntry(ref="ghcr.io/owner/repo/zed-capture", digest="sha256:abc", tags=["tree-1"]),
        "aoa-bridge": DigestEntry(ref="ghcr.io/owner/repo/aoa-bridge", digest="sha256:def", tags=["tree-2"]),
    }
    patch_image_manifest(monkeypatch, tmp_path)
    patch_context(monkeypatch, PublishConfig())
    patch_pull_artifact(monkeypatch, digest_layer(manifest))
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)
    written = capturing_bash(monkeypatch)

    release_module.main(channel=ReleaseChannel.PR)

    assert written
    assert written[0].index("| aoa-bridge |") < written[0].index("| zed-capture |")


def test_update_pr_draft_omits_images_when_not_declared(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_context(monkeypatch, make_build_config())
    patch_pull_artifact(monkeypatch, {("MyApp", "AndroidMobile"): {"MyApp.apk": "build content"}})
    patch_plan_tags(monkeypatch, FakeTags(versions={"myapp": "1.0.0"}, changed=set()))
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)
    written = capturing_bash(monkeypatch)

    release_module.main(channel=ReleaseChannel.PR)

    assert written
    assert "Built images" not in written[0]


def test_update_pr_draft_lists_images_without_any_apps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest = {"zed-capture": DigestEntry(ref="ghcr.io/owner/repo/zed-capture", digest="sha256:abc", tags=["tree-1"])}
    patch_image_manifest(monkeypatch, tmp_path)
    config = PublishConfig(apps={})
    patch_context(monkeypatch, config)
    patch_pull_artifact(monkeypatch, digest_layer(manifest))
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)
    written = capturing_bash(monkeypatch)

    release_module.main(channel=ReleaseChannel.PR)

    assert written
    assert "| zed-capture | [`tree-1`](https://github.com/owner/repo/pkgs/container/repo%2Fzed-capture) |" in written[0]
    assert "sha256:abc" not in written[0]


def test_update_pr_draft_merges_digest_shards(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shard_a = {"zed-capture": DigestEntry(ref="ghcr.io/owner/repo/zed-capture", digest="sha256:abc", tags=["tree-1"])}
    shard_b = {"aoa-bridge": DigestEntry(ref="ghcr.io/owner/repo/aoa-bridge", digest="sha256:def", tags=["tree-2"])}
    patch_image_manifest(monkeypatch, tmp_path)
    patch_context(monkeypatch, PublishConfig())
    patch_pull_artifact(
        monkeypatch,
        {
            **shard_layer(f"sha-{CERTIFIED_SHA}-aaaaaaaa", shard_a),
            **shard_layer(f"sha-{CERTIFIED_SHA}-bbbbbbbb", shard_b),
        },
    )
    monkeypatch.setattr(
        release_module,
        "list_build_tags",
        FixedReturn([f"sha-{CERTIFIED_SHA}-aaaaaaaa", f"sha-{CERTIFIED_SHA}-bbbbbbbb"]),
    )
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)
    written = capturing_bash(monkeypatch)

    release_module.main(channel=ReleaseChannel.PR)

    assert written
    assert "zed-capture" in written[0]
    assert "aoa-bridge" in written[0]


def test_update_pr_draft_fails_loudly_on_overlapping_shards(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shard_a = {"zed-capture": DigestEntry(ref="ghcr.io/owner/repo/zed-capture", digest="sha256:abc", tags=["tree-1"])}
    shard_b = {"zed-capture": DigestEntry(ref="ghcr.io/owner/repo/zed-capture", digest="sha256:abc", tags=["tree-1"])}
    patch_image_manifest(monkeypatch, tmp_path)
    patch_context(monkeypatch, PublishConfig())
    patch_pull_artifact(
        monkeypatch,
        {
            **shard_layer(f"sha-{CERTIFIED_SHA}-aaaaaaaa", shard_a),
            **shard_layer(f"sha-{CERTIFIED_SHA}-bbbbbbbb", shard_b),
        },
    )
    monkeypatch.setattr(
        release_module,
        "list_build_tags",
        FixedReturn([f"sha-{CERTIFIED_SHA}-aaaaaaaa", f"sha-{CERTIFIED_SHA}-bbbbbbbb"]),
    )
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)

    with pytest.raises(SystemExit, match="repeats target"):
        release_module.main(channel=ReleaseChannel.PR)


def test_update_pr_draft_fails_loudly_on_treeless_manifest_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw_manifest = {
        "zed-capture": {"ref": "ghcr.io/owner/repo/zed-capture", "digest": "sha256:abc", "tags": ["latest"]}
    }
    patch_image_manifest(monkeypatch, tmp_path)
    patch_context(monkeypatch, PublishConfig())
    patch_pull_artifact(monkeypatch, {("images-digests", "all"): {DIGEST_FILE_NAME: json.dumps(raw_manifest)}})
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)

    with pytest.raises(ValueError, match="tree-"):
        release_module.main(channel=ReleaseChannel.PR)


def test_update_pr_draft_fails_loudly_on_foreign_registry_ref(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    raw_manifest = {
        "zed-capture": {"ref": "registry.example.com/owner/zed-capture", "digest": "sha256:abc", "tags": ["tree-1"]}
    }
    patch_image_manifest(monkeypatch, tmp_path)
    patch_context(monkeypatch, PublishConfig())
    patch_pull_artifact(monkeypatch, {("images-digests", "all"): {DIGEST_FILE_NAME: json.dumps(raw_manifest)}})
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)

    with pytest.raises(ValueError, match=r"ghcr\.io"):
        release_module.main(channel=ReleaseChannel.PR)


def test_update_pr_draft_no_apps_uploads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_context(monkeypatch, PublishConfig())
    patch_pr_bash_output(monkeypatch)
    bash_log = patch_bash(monkeypatch, check_returns=False)

    release_module.main(channel=ReleaseChannel.PR)

    assert not any("gh release upload" in command for command in bash_log.commands)
    assert any("gh release edit pr-107" in command for command in bash_log.commands)


def test_update_pr_draft_refuses_non_pull_request_wake(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_context(monkeypatch, make_build_config(), github_ref="refs/heads/dev")
    patch_pr_bash_output(monkeypatch)
    bash_log = patch_bash(monkeypatch, check_returns=False)

    with pytest.raises(IndexError):
        release_module.main(channel=ReleaseChannel.PR)

    assert bash_log.commands == ["git config --global --add safe.directory /workspace"]


def test_update_pr_draft_writes_notes_file_without_recreating(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_context(monkeypatch, PublishConfig())
    patch_pr_bash_output(monkeypatch)
    bash_log = patch_bash(monkeypatch, check_returns=True)

    release_module.main(channel=ReleaseChannel.PR)

    assert any("gh release edit pr-107" in command and "--notes-file" in command for command in bash_log.commands)
    assert not any("gh release create" in command for command in bash_log.commands)


def test_update_pr_draft_creates_missing_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_context(monkeypatch, PublishConfig())
    patch_pr_bash_output(monkeypatch)
    bash_log = patch_bash(monkeypatch, check_returns=False)

    release_module.main(channel=ReleaseChannel.PR)

    assert any(
        "gh release create pr-107" in command and "--draft" in command and f"--target {CERTIFIED_SHA}" in command
        for command in bash_log.commands
    )
    assert any("gh release edit pr-107" in command and "--notes-file" in command for command in bash_log.commands)


def test_update_pr_draft_replaces_same_anchor_and_preserves_others(monkeypatch: pytest.MonkeyPatch) -> None:
    body = f'<a id="sha-old"></a>\n### Old\n\n<a id="sha-{SHORT_SHA}"></a>\n### New v1'
    patch_context(monkeypatch, PublishConfig())
    patch_pr_bash_output(monkeypatch, body)
    patch_bash(monkeypatch, check_returns=True)
    written = capturing_bash(monkeypatch)

    release_module.main(channel=ReleaseChannel.PR)

    assert written
    assert "### Old" in written[0]
    assert f"### Commit [{SHORT_SHA}]" in written[0]
    assert "### New v1" not in written[0]


def test_update_pr_draft_lists_one_row_per_staged_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PublishConfig(
        apps={
            "myapp": AppConfig(
                path=Path("apps/myapp"),
                major_minor="1.0",
                builds=[
                    BuildArtifactConfig(project="MyApp", platform="AndroidMobile", file="MyApp-AndroidMobile.apk"),
                    BuildArtifactConfig(project="MyApp", platform="IOS", file="MyApp-IOS.apk"),
                ],
            )
        },
    )
    patch_context(monkeypatch, config)
    patch_plan_tags(monkeypatch, FakeTags(versions={"myapp": "1.0.0"}, changed=set()))
    patch_pull_artifact(
        monkeypatch,
        {
            ("MyApp", "AndroidMobile"): {"MyApp-AndroidMobile.apk": "build content"},
            ("MyApp", "IOS"): {"MyApp-IOS.apk": "build content"},
        },
    )
    patch_pr_bash_output(monkeypatch)
    patch_bash(monkeypatch, check_returns=False)
    written = capturing_bash(monkeypatch)

    release_module.main(channel=ReleaseChannel.PR)

    assert written
    assert (
        f"| myapp | AndroidMobile | [1.0.0]"
        f"(https://github.com/owner/repo/releases/download/pr-107/MyApp-AndroidMobile-{COMMIT_COUNT}.apk) |"
    ) in written[0]
    assert (
        f"| myapp | IOS | [1.0.0]"
        f"(https://github.com/owner/repo/releases/download/pr-107/MyApp-IOS-{COMMIT_COUNT}.apk) |"
    ) in written[0]
