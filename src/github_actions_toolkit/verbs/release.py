from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
from datetime import UTC, datetime
from enum import StrEnum
from operator import itemgetter
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import NamedTemporaryFile, mkdtemp
from time import sleep
from typing import Annotated, NamedTuple, Self

import typer
from bashrun.bash import bash, bash_check, bash_output
from build_artifact_registry.builds import list_build_tags, pull_artifact
from build_artifact_registry.setup_oras import install_oras
from pydantic import BaseModel, model_validator

from github_actions_toolkit.config import (
    DEFAULT_CONFIG_PATH,
    IMAGE_MANIFEST_PATH,
    PublishConfig,
    Settings,
    load_config,
)
from github_actions_toolkit.plan import (
    UNCHANGED_FALLBACK_VERSION,
    ReleasePlan,
    app_base_version,
    compute_release_plan,
    get_latest_version,
)
from github_actions_toolkit.publishing import build_registries
from github_actions_toolkit.releases import delete_releases_by_prefix, sweep_superseded_pr_releases

DIGEST_PROJECT = "images-digests"
DIGEST_PLATFORM = "all"
DIGEST_FILE_NAME = "images-digests.json"


class ReleaseChannel(StrEnum):
    STABLE = "stable"
    DEV = "dev"
    PR = "pr"


class DigestEntry(BaseModel):
    ref: str
    digest: str
    tags: list[str]

    @model_validator(mode="after")
    def require_tree_tag(self) -> Self:
        if not any(tag.startswith("tree-") for tag in self.tags):
            raise ValueError(f"entry '{self.ref}' carries no tree- tag")
        return self


class PackageRow(NamedTuple):
    name: str
    version: str
    registry: str
    url: str | None


class StagedAsset(NamedTuple):
    app_name: str
    platform: str
    path: Path


class LandedPr(NamedTuple):
    number: str
    title: str
    head_sha: str


app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


@app.command()
def main(
    channel: Annotated[
        ReleaseChannel, typer.Option(help="Delivery channel: pr/dev per-run prerelease, stable release")
    ],
    config: Annotated[Path, typer.Option(help="Publish configuration YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    # Read the runner settings and the publish config
    settings = Settings.model_validate({})
    publish_config = load_config(config)

    # Make git trust the workspace before any git call
    # Re-set safe.directory in the real HOME, where checkout only wrote a temporary one
    bash(f"git config --global --add safe.directory {shlex.quote(settings.github_workspace)}")

    # Publish every changed package to its registry and tag the stable versions
    release_plan = compute_release_plan(publish_config)

    # Stop a run with nothing to ship, before creating anything
    match channel:
        case ReleaseChannel.PR:
            if not publish_config.apps and not IMAGE_MANIFEST_PATH.is_file():
                return
        case ReleaseChannel.DEV:
            if not release_plan.publishing and not publish_config.apps and not IMAGE_MANIFEST_PATH.is_file():
                return
        case ReleaseChannel.STABLE:
            if not release_plan.publishing and not release_plan.app_versions:
                return

    # Resolve the landed PR and the certified head SHA for the channel
    repository = settings.github_repository
    head = bash_output("git rev-parse HEAD").strip()
    landed = resolve_landed_pr(repository, head) if channel != ReleaseChannel.PR else None
    sha = landed.head_sha if landed else head
    short_sha = sha[:12]

    # Squash and rebase merges write new commits, leaving the certified head reachable only through the PR ref
    if landed and not bash_check(f"git cat-file -e {sha}"):
        bash(f"git fetch origin refs/pull/{landed.number}/head")

    # Count commits at the certified head the app binaries were stamped from
    commit_count = int(bash_output(f"git rev-list --count {sha}").strip()) if channel != ReleaseChannel.STABLE else 0

    # Stable tags names by CalVer instead of the count, but its assets still carry the certified head's stamp
    asset_count = (
        commit_count if channel != ReleaseChannel.STABLE else int(bash_output(f"git rev-list --count {sha}").strip())
    )

    # Lay out the release notes scaffolding
    heading = f"### Commit [{short_sha}](https://github.com/{repository}/commit/{sha})"
    blocks: list[str] = []

    # Compose the channel's tag, title, versions, and header
    match channel:
        case ReleaseChannel.PR:
            pr_number = re.findall(r"^refs/pull/(\d+)/merge$", settings.github_ref)[0]
            tag = f"pr-{pr_number}-{commit_count}"
            title = f"PR #{pr_number} · {short_sha} · build {commit_count}"
            blocks.append(heading)

        case ReleaseChannel.DEV:
            tag = f"dev-{commit_count}"

            if landed:
                title = f"dev build {commit_count} · PR #{landed.number}: {landed.title}"
                blocks.append(
                    f"{heading} — [PR #{landed.number}: {landed.title}]"
                    f"(https://github.com/{repository}/pull/{landed.number})"
                )
            else:
                title = f"dev build {commit_count} · {short_sha}"
                blocks.append(heading)

        case ReleaseChannel.STABLE:
            year_month = datetime.now(UTC).strftime("%Y.%m")
            existing = bash_output(
                f"gh release list --repo {settings.github_repository} --json tagName"
                f" --jq '[.[].tagName] | map(select(startswith(\"{year_month}\"))) | length'"
            ).strip()
            tag = f"{year_month}.{(int(existing) if existing else 0) + 1}"
            title = tag
            blocks.append(heading)

    versions = stamped_app_versions(publish_config, release_plan, channel, asset_count)

    # A published release at this tag is a re-run of the same run: notes rewrite only.
    # A leftover draft is a botched prior run: drafts are disposable, start over
    view_command = f"gh release view {tag} --repo {repository}"
    rerun = False
    if bash_check(view_command):
        if json.loads(bash_output(f"{view_command} --json isDraft"))["isDraft"]:
            bash(f"gh release delete {tag} --yes --repo {repository}")
        else:
            rerun = True
    if not rerun:
        bash(
            f"gh release create {tag} --draft --target {head} --title {shlex.quote(title)}"
            f" --notes '' --repo {repository}"
        )

    # Publish the changed packages and tag the stable versions
    if channel in (ReleaseChannel.DEV, ReleaseChannel.STABLE):
        packages = publish_packages(settings, publish_config, release_plan, channel, commit_count)
        if packages:
            packages_rows = [
                [name, registry, f"[{version}]({url})" if url else version] for name, version, registry, url in packages
            ]
            blocks.append(f"## Packages\n{markdown_table(['Package', 'Registry', 'Version'], packages_rows)}")

    # Stage every app's build artifacts as release assets on the draft
    shelf = f"ghcr.io/{repository.lower()}/builds"
    if not rerun and publish_config.apps:
        stage_apps(settings, publish_config, shelf, release_plan, channel, sha, commit_count, tag, repository)

    # Publish the release so its assets take their stable tag-form addresses
    if not rerun:
        if channel in (ReleaseChannel.PR, ReleaseChannel.DEV):
            bash(f"gh release edit {tag} --draft=false --prerelease --repo {repository}")
        else:
            bash(f"gh release edit {tag} --draft=false --repo {repository}")

    # Read back the served asset URLs from the published release
    download_urls: dict[str, str] = {}
    if publish_config.apps:
        served_assets = json.loads(bash_output(f"{view_command} --json assets"))["assets"]
        download_urls = {asset["name"]: asset["url"] for asset in served_assets}
        assets_rows = [
            [
                app_name,
                artifact.platform,
                f"[{versions[app_name]}]({download_urls[release_asset_name(artifact.file, channel, commit_count)]})",
            ]
            for app_name, app in publish_config.apps.items()
            for artifact in app.builds
        ]
        blocks.append(f"## Apps\n{markdown_table(['App', 'Platform', 'Version'], assets_rows)}")

    # List the images built at this SHA from the shelf, declared by the image manifest's presence
    if IMAGE_MANIFEST_PATH.is_file():
        images = pull_digest_manifest(settings, shelf, sha)
        if images:
            images_rows: list[list[str]] = []
            for entry in sorted(images.values(), key=lambda entry: entry.ref):
                # Strip the repository namespace every ref must live under; ghcr
                # stores every path lowercase, so the prefix must match that form
                repository_prefix = f"ghcr.io/{repository.lower()}/"
                if not entry.ref.startswith(repository_prefix):
                    raise ValueError(f"image ref '{entry.ref}' does not live under {repository_prefix.rstrip('/')}")
                display_name = entry.ref[len(repository_prefix) :]

                # Link the tree- tag to that exact package version's page
                image_tag = next(candidate for candidate in entry.tags if candidate.startswith("tree-"))
                owner, package = entry.ref[len("ghcr.io/") :].split("/", 1)
                package_path = package.replace("/", "%2F")
                page = f"https://github.com/{settings.github_repository}/pkgs/container/{package_path}"
                version_id = package_version_id(owner, package, entry.digest)
                url = f"{page}/{version_id}?tag={image_tag}" if version_id else page
                images_rows.append([display_name, f"[`{image_tag}`]({url})"])
            blocks.append(f"## Built images\n{markdown_table(['Image', 'Tag'], images_rows)}")

    # Apply the notes to the release from a temp file
    notes = "\n\n".join(blocks) + "\n"
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as file:
        file.write(notes)
        notes_path = file.name

    try:
        bash(f"gh release edit {tag} --repo {repository} --notes-file {notes_path}")
    finally:
        Path(notes_path).unlink()

    # Append the run summary for the run page
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        release_url = json.loads(bash_output(f"{view_command} --json url"))["url"]
        summary_lines = [f"## Run release\n\n{release_url}"]
        summary_lines += [f"- [{name}]({url})" for name, url in sorted(download_urls.items())]
        with open(summary_path, "a", encoding="utf-8") as file:
            file.write("\n".join(summary_lines) + "\n")

    # Sweep the PR's superseded builds once this run's prerelease is complete
    if channel == ReleaseChannel.PR:
        sweep_superseded_pr_releases(tag, repository)

    # Sweep the dev releases once the stable release is cut
    if channel == ReleaseChannel.STABLE:
        delete_releases_by_prefix("dev-", repository)


def resolve_landed_pr(repository: str, head: str) -> LandedPr | None:
    # The PR database, not the landing's commit shape or message, is the record of what landed
    pulls = json.loads(bash_output_with_retry(f"gh api repos/{repository}/commits/{head}/pulls"))
    landed = [pull for pull in pulls if pull["merged_at"] is not None and pull["merge_commit_sha"] == head]
    if not landed:
        return None
    pull = max(landed, key=itemgetter("number"))
    return LandedPr(str(pull["number"]), pull["title"], pull["head"]["sha"])


def bash_output_with_retry(command: str, attempts: int = 3, backoff_seconds: float = 5.0) -> str:
    # gh hides the HTTP status behind an empty-body 5xx (cli/cli#10579), so every failure reads as potentially transient
    for attempt in range(1, attempts):
        try:
            return bash_output(command)
        except CalledProcessError:
            wait_seconds = backoff_seconds * 2 ** (attempt - 1)
            print(f"{command} failed on attempt {attempt} of {attempts}, retrying in {wait_seconds:.0f}s")
            sleep(wait_seconds)
    return bash_output(command)


def stamped_app_versions(
    publish_config: PublishConfig, release_plan: ReleasePlan, channel: ReleaseChannel, asset_count: int
) -> dict[str, str]:
    stamped: dict[str, str] = {}
    for app_name, app_config in publish_config.apps.items():
        base = release_plan.app_versions.get(app_name) if channel == ReleaseChannel.STABLE else None
        if base is None:
            base = app_base_version(app_config, app_name)
        stamped[app_name] = f"{base}+{asset_count}"
    return stamped


def publish_packages(
    settings: Settings,
    publish_config: PublishConfig,
    release_plan: ReleasePlan,
    channel: ReleaseChannel,
    commit_count: int,
) -> list[PackageRow]:
    # Provision the toolchains for the registries this run publishes to
    publishing_registries = {publish_config.packages[name].registry for name in release_plan.publishing}

    if "nuget" in publishing_registries:
        # Install the .NET SDK through the vendored install script
        dotnet_channel = "8.0"
        print(f"Installing .NET SDK {dotnet_channel}")
        script = Path(__file__).parent.parent / "third-party" / "dotnet-install.sh"
        bash(f"bash {script} --channel {dotnet_channel}")

        # Put dotnet on PATH for this process and the rest of the job
        dotnet_path = str(Path.home() / ".dotnet")
        os.environ["PATH"] = f"{dotnet_path}{os.pathsep}{os.environ['PATH']}"
        if settings.github_path:
            with open(settings.github_path, "a") as file:
                file.write(f"{dotnet_path}\n")

    if "npm" in publishing_registries:
        # Resolve the current linux-x64 tarball from the official shasums listing
        node_version = "24"
        print(f"Installing Node.js {node_version}")
        shasums = bash_output(f"curl -fsSL https://nodejs.org/dist/latest-v{node_version}.x/SHASUMS256.txt")
        match = re.search(r"(node-v[\d.]+-linux-x64\.tar\.xz)", shasums)
        if not match:
            raise SystemExit(f"Could not find Node.js v{node_version} linux-x64 binary")
        filename = match.group(1)

        # Unpack over /usr/local, dropping the runner's preinstalled npm
        sudo_prefix = "sudo " if platform.system() == "Linux" and os.geteuid() != 0 else ""
        bash(f"curl -fsSLO https://nodejs.org/dist/latest-v{node_version}.x/{filename}")
        bash(f"{sudo_prefix}rm -rf /usr/local/lib/node_modules/npm")
        bash(f"{sudo_prefix}tar -xJf {filename} -C /usr/local --strip-components=1")
        Path(filename).unlink()

        # Point npm at the public registry
        (Path.home() / ".npmrc").write_text("registry=https://registry.npmjs.org\n")

    # Build the registry adapters the package loop publishes through
    registries = build_registries(settings.nuget_api_key)
    dev = channel == ReleaseChannel.DEV
    rows: list[PackageRow] = []
    for name, package in publish_config.packages.items():
        plan = release_plan.plans[name]
        registry = registries[package.registry]
        latest_version = get_latest_version(f"{name}-v")

        # List an unchanged package at its latest stable tag
        if not plan.publish and latest_version is not None:
            rows.append(
                PackageRow(name, latest_version, package.registry, registry.url(package.identity, latest_version))
            )
            continue

        # List a never-published package with the fallback version
        if not plan.publish:
            rows.append(PackageRow(name, UNCHANGED_FALLBACK_VERSION, package.registry, None))
            continue

        # Publish the changed package and list the version it returned
        version = registry.publish(
            package.path,
            plan.version,
            release_plan.resolved_versions[name],
            dev,
            commit_count,
        )

        if channel == ReleaseChannel.STABLE:
            create_and_push_tag(f"{name}-v{plan.version}")

        rows.append(PackageRow(name, version, package.registry, registry.url(package.identity, version)))

    return rows


def stage_apps(
    settings: Settings,
    publish_config: PublishConfig,
    shelf: str,
    release_plan: ReleasePlan,
    channel: ReleaseChannel,
    sha: str,
    commit_count: int,
    tag: str,
    repository: str,
) -> list[StagedAsset]:
    install_oras()
    staging = Path(mkdtemp(prefix="release-builds-"))
    staged: list[StagedAsset] = []
    for app_name, artifact in [
        (app_name, artifact) for app_name, app in publish_config.apps.items() for artifact in app.builds
    ]:
        # Pull the artifact layer from the builds shelf
        layer = staging / f"{artifact.project}-{artifact.platform}"

        pull_artifact(
            shelf,
            artifact.project,
            artifact.platform,
            f"sha-{sha}",
            layer,
            registry_username=settings.github_actor,
            registry_token=settings.github_token,
        )

        # Unwrap the layer's single file, the build's player binary
        (source,) = layer.iterdir()

        # Copy the asset under its release name and record it
        target = staging / release_asset_name(artifact.file, channel, commit_count)
        shutil.copy2(source, target)
        staged.append(StagedAsset(app_name, artifact.platform, target))

    # Tag the bumped app versions alongside their staged assets
    if channel == ReleaseChannel.STABLE:
        for app_name, app_version in release_plan.app_versions.items():
            create_and_push_tag(f"{app_name}-v{app_version}")

    # Upload the staged assets
    upload_paths = " ".join(f'"{path}"' for _, _, path in staged)
    bash(f"gh release upload {tag} {upload_paths} --clobber --repo {repository}")

    return staged


def pull_digest_manifest(settings: Settings, shelf: str, sha: str) -> dict[str, DigestEntry]:
    install_oras()
    # Enumerate the SHA's shards, one tag per parallel matrix leg
    shard_prefix = f"sha-{sha}-"
    shard_tags = sorted(
        tag
        for tag in list_build_tags(
            shelf,
            DIGEST_PROJECT,
            DIGEST_PLATFORM,
            registry_username=settings.github_actor,
            registry_token=settings.github_token,
        )
        if tag.startswith(shard_prefix)
    )
    # Fall back to the bare pre-shard tag when no shards exist
    if not shard_tags:
        shard_tags = [f"sha-{sha}"]
    merged: dict[str, DigestEntry] = {}
    for shard_tag in shard_tags:
        digest_staging = Path(mkdtemp(prefix="digest-manifest-"))
        pull_artifact(
            shelf,
            DIGEST_PROJECT,
            DIGEST_PLATFORM,
            shard_tag,
            digest_staging,
            registry_username=settings.github_actor,
            registry_token=settings.github_token,
        )
        data = json.loads((digest_staging / DIGEST_FILE_NAME).read_text(encoding="utf-8"))
        for target, entry in data.items():
            if target in merged:
                raise SystemExit(f"digest shard '{shard_tag}' repeats target '{target}' from another shard")
            merged[target] = DigestEntry.model_validate(entry)
    return merged


def create_and_push_tag(tag: str) -> None:
    bash(f"git tag {tag}")
    bash(f"git push origin {tag}")


def package_version_id(owner: str, package: str, digest: str) -> int | None:
    try:
        versions = bash_output(
            f"gh api /orgs/{owner}/packages/container/{package.replace('/', '%2F')}/versions?per_page=100"
        )
    except CalledProcessError:
        return None
    for version in json.loads(versions):
        if version["name"] == digest:
            return version["id"]
    return None


def release_asset_name(file: str, channel: ReleaseChannel, commit_count: int) -> str:
    file_path = Path(file)
    return file_path.name if channel == ReleaseChannel.STABLE else f"{file_path.stem}-{commit_count}{file_path.suffix}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [f"| {' | '.join(headers)} |", f"|{'|'.join('---' for _ in headers)}|"]
    lines.extend(f"| {' | '.join(row)} |" for row in rows)
    return "\n".join(lines)
