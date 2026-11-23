import json
from pathlib import Path
from subprocess import CalledProcessError
from zipfile import ZipFile

import pytest
from bashrun.bash import bash

from github_actions_toolkit.publishing import NpmRegistry, NuGetRegistry, ResolvedDependency
from github_actions_toolkit.publishing import (
    BUILD_COMMIT_STAMP,
    PyPIRegistry,
    ephemeral_commit_stamp,
    ephemeral_manifest_patch,
    ephemeral_pyproject_patch,
)

PYPROJECT = (
    "[project]\n"
    'name = "example"\n'
    'version = "0.0.0.dev0"\n'
    'dependencies = ["pydantic>=2"]\n'
    "\n"
    "[tool.hatch.version]\n"
    'version = "not-this-one"\n'
    "\n"
    "[build-system]\n"
    'requires = ["hatchling"]\n'
)

PYPROJECT_WITH_SENTINELS = (
    "[project]\n"
    'name = "example"\n'
    'version = "0.0.0.dev0"\n'
    "dependencies = [\n"
    '    "sibling==0.0.0+local",\n'
    '    "pydantic>=2",\n'
    "]\n"
    "\n"
    "[tool.uv.sources]\n"
    "sibling = { workspace = true }\n"
)

PYPROJECT_BUILDABLE = (
    "[project]\n"
    'name = "example"\n'
    'version = "0.0.0.dev0"\n'
    "\n"
    "[build-system]\n"
    'requires = ["hatchling"]\n'
    'build-backend = "hatchling.build"\n'
)


class CommandRecorder:
    def __init__(self, result: str = "") -> None:
        self.commands: list[str] = []
        self.result = result

    def __call__(
        self,
        command: str,
        *,
        cwd: Path | None = None,
        stdin_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        self.commands.append(command)
        return self.result


def write_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "package.json"
    manifest_path.write_text(
        json.dumps({
            "name": "org.outernet.placeframe",
            "version": "0.0.0-local",
            "dependencies": {"org.outernet.placeframe.apiclient": "0.0.0+local"},
        }),
        encoding="utf-8",
    )
    return manifest_path


def test_patch_updates_version_and_pins_then_restores(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)

    with ephemeral_manifest_patch(tmp_path, "0.2.1", {"org.outernet.placeframe.apiclient": "0.1.8"}):
        patched = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert patched["version"] == "0.2.1"
        assert patched["dependencies"] == {"org.outernet.placeframe.apiclient": "0.1.8"}

    restored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert restored["version"] == "0.0.0-local"
    assert restored["dependencies"] == {"org.outernet.placeframe.apiclient": "0.0.0+local"}


def test_patch_skips_dependency_keys_absent_from_the_manifest(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)

    with ephemeral_manifest_patch(tmp_path, "0.2.1", {"some.pypi.sibling": "0.3.0"}):
        patched = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert patched["dependencies"] == {"org.outernet.placeframe.apiclient": "0.0.0+local"}


def test_patch_restores_on_error(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)
    original = manifest_path.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError), ephemeral_manifest_patch(tmp_path, "0.2.1", {}):
        raise RuntimeError("publish exploded")

    assert manifest_path.read_text(encoding="utf-8") == original


def test_ephemeral_pyproject_patch_restores_the_original(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pyproject.toml"
    manifest_path.write_text(PYPROJECT, encoding="utf-8")

    with ephemeral_pyproject_patch(tmp_path, "0.2.0", {}):
        assert 'version = "0.2.0"' in manifest_path.read_text(encoding="utf-8")

    assert manifest_path.read_text(encoding="utf-8") == PYPROJECT


def test_ephemeral_pyproject_patch_restores_on_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pyproject.toml"
    manifest_path.write_text(PYPROJECT, encoding="utf-8")

    with pytest.raises(RuntimeError), ephemeral_pyproject_patch(tmp_path, "0.2.0", {}):
        raise RuntimeError("publish exploded")

    assert manifest_path.read_text(encoding="utf-8") == PYPROJECT


def test_ephemeral_pyproject_patch_rewrites_sentinel_specifiers(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pyproject.toml"
    manifest_path.write_text(PYPROJECT_WITH_SENTINELS, encoding="utf-8")

    with ephemeral_pyproject_patch(tmp_path, "0.2.0", {"sibling": "1.0.4"}):
        patched = manifest_path.read_text(encoding="utf-8")
        assert 'version = "0.2.0"' in patched
        assert '"sibling==1.0.4"' in patched
        assert "0.0.0+local" not in patched
        assert '"pydantic>=2"' in patched

    assert manifest_path.read_text(encoding="utf-8") == PYPROJECT_WITH_SENTINELS


def write_src_package(tmp_path: Path) -> Path:
    package_directory = tmp_path / "src" / "example"
    package_directory.mkdir(parents=True)
    (package_directory / "__init__.py").write_text("", encoding="utf-8")
    return package_directory


def test_commit_stamp_exists_inside_the_window_and_vanishes_after(tmp_path: Path) -> None:
    package_directory = write_src_package(tmp_path)
    stamp_path = package_directory / BUILD_COMMIT_STAMP

    with ephemeral_commit_stamp(tmp_path, "a" * 40):
        assert stamp_path.read_text(encoding="utf-8") == f"{'a' * 40}\n"

    assert not stamp_path.exists()


def test_commit_stamp_restores_a_preexisting_stamp(tmp_path: Path) -> None:
    package_directory = write_src_package(tmp_path)
    stamp_path = package_directory / BUILD_COMMIT_STAMP
    stamp_path.write_text(f"{'0' * 40}\n", encoding="utf-8")

    with ephemeral_commit_stamp(tmp_path, "a" * 40):
        assert stamp_path.read_text(encoding="utf-8") == f"{'a' * 40}\n"

    assert stamp_path.read_text(encoding="utf-8") == f"{'0' * 40}\n"


def test_commit_stamp_vanishes_on_error(tmp_path: Path) -> None:
    package_directory = write_src_package(tmp_path)

    with pytest.raises(RuntimeError), ephemeral_commit_stamp(tmp_path, "a" * 40):
        raise RuntimeError("publish exploded")

    assert not (package_directory / BUILD_COMMIT_STAMP).exists()


def test_commit_stamp_without_a_sha_is_loud(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"GITHUB_SHA is empty"):
        with ephemeral_commit_stamp(tmp_path, ""):
            pass


def test_commit_stamp_without_src_layout_is_loud(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"no src/ directory"):
        with ephemeral_commit_stamp(tmp_path, "a" * 40):
            pass


def test_commit_stamp_with_empty_src_is_loud(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()

    with pytest.raises(ValueError, match=r"found: none"):
        with ephemeral_commit_stamp(tmp_path, "a" * 40):
            pass


def test_commit_stamp_with_ambiguous_src_is_loud(tmp_path: Path) -> None:
    (tmp_path / "src" / "one").mkdir(parents=True)
    (tmp_path / "src" / "two").mkdir(parents=True)

    with pytest.raises(ValueError, match=r"found: one, two"):
        with ephemeral_commit_stamp(tmp_path, "a" * 40):
            pass


def test_pypi_publish_builds_inside_the_stamp_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    package_directory = write_src_package(tmp_path)
    stamped: dict[str, str] = {}

    def recording_build(
        command: str,
        *,
        cwd: Path | None = None,
        stdin_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        if "uv build" in command:
            stamped["content"] = (package_directory / BUILD_COMMIT_STAMP).read_text(encoding="utf-8")
        return ""

    monkeypatch.setattr("github_actions_toolkit.publishing.bash", recording_build)

    PyPIRegistry("b" * 40).publish(tmp_path, "0.2.0", {}, False, 0)

    assert stamped["content"] == f"{'b' * 40}\n"
    assert not (package_directory / BUILD_COMMIT_STAMP).exists()


def test_commit_stamp_rides_the_wheel(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_BUILDABLE, encoding="utf-8")
    package_directory = write_src_package(tmp_path)

    with ephemeral_commit_stamp(tmp_path, "c" * 40):
        bash("uv build --out-dir dist", cwd=tmp_path)

    wheel_path = next((tmp_path / "dist").glob("*.whl"))
    with ZipFile(wheel_path) as archive:
        stamp_content = archive.read(f"example/{BUILD_COMMIT_STAMP}").decode(encoding="utf-8")

    assert stamp_content == f"{'c' * 40}\n"
    assert not (package_directory / BUILD_COMMIT_STAMP).exists()


def test_npm_publish_rides_the_dev_dist_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = write_manifest(tmp_path)
    recorder = CommandRecorder()
    monkeypatch.setattr("github_actions_toolkit.publishing.bash_output", recorder)

    NpmRegistry().publish(
        path=tmp_path,
        base_version="0.2.1",
        resolved_dependencies={},
        dev=True,
        commit_count=42,
    )

    assert recorder.commands == ["npm publish --access public --provenance --loglevel verbose --tag dev"]
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["version"] == "0.0.0-local"


def write_locked_build_package(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "package.json"
    manifest_path.write_text(
        json.dumps({
            "name": "@placeframe/api-client",
            "version": "0.0.0-local",
            "scripts": {"build": "tsc", "prepare": "npm run build"},
            "devDependencies": {"typescript": "5.9.3"},
        }),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {}}), encoding="utf-8")
    return manifest_path


def test_npm_publish_installs_the_locked_build_toolchain_before_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_locked_build_package(tmp_path)
    recorder = CommandRecorder()
    monkeypatch.setattr("github_actions_toolkit.publishing.bash", recorder)
    monkeypatch.setattr("github_actions_toolkit.publishing.bash_output", recorder)

    NpmRegistry().publish(tmp_path, "0.2.1", {}, True, 42)

    assert recorder.commands == [
        "npm ci --no-audit --no-fund",
        "npm publish --access public --provenance --loglevel verbose --tag dev",
    ]


def test_npm_publish_installs_the_lockfile_even_without_build_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_manifest(tmp_path)
    (tmp_path / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {}}), encoding="utf-8")
    recorder = CommandRecorder()
    monkeypatch.setattr("github_actions_toolkit.publishing.bash", recorder)
    monkeypatch.setattr("github_actions_toolkit.publishing.bash_output", recorder)

    NpmRegistry().publish(tmp_path, "0.2.1", {}, False, 0)

    assert recorder.commands == [
        "npm ci --no-audit --no-fund",
        "npm publish --access public --provenance --loglevel verbose",
    ]


def test_npm_publish_with_build_script_but_no_lockfile_is_loud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({
            "name": "@placeframe/api-client",
            "version": "0.0.0-local",
            "scripts": {"prepare": "npm run build"},
        }),
        encoding="utf-8",
    )
    recorder = CommandRecorder()
    monkeypatch.setattr("github_actions_toolkit.publishing.bash", recorder)
    monkeypatch.setattr("github_actions_toolkit.publishing.bash_output", recorder)

    with pytest.raises(ValueError, match=r"runs build lifecycle scripts \['prepare'\] during publish"):
        NpmRegistry().publish(tmp_path, "0.2.1", {}, False, 0)

    assert recorder.commands == []


def test_npm_publish_without_dist_tag_leaves_latest_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_manifest(tmp_path)
    recorder = CommandRecorder()
    monkeypatch.setattr("github_actions_toolkit.publishing.bash_output", recorder)

    NpmRegistry().publish(tmp_path, "0.2.1", {}, False, 0)

    assert recorder.commands == ["npm publish --access public --provenance --loglevel verbose"]


def test_npm_publish_prints_the_command_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_manifest(tmp_path)
    monkeypatch.setattr(
        "github_actions_toolkit.publishing.bash_output", CommandRecorder("+ org.outernet.placeframe@0.2.1\n")
    )

    NpmRegistry().publish(tmp_path, "0.2.1", {}, False, 0)

    assert "+ org.outernet.placeframe@0.2.1" in capsys.readouterr().out


class ConflictingCommand:
    def __init__(self, stderr: str) -> None:
        self.stderr = stderr

    def __call__(
        self,
        command: str,
        *,
        cwd: Path | None = None,
        stdin_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        raise CalledProcessError(returncode=1, cmd=command, stderr=self.stderr)


def test_npm_publish_swallows_version_conflict_from_current_npm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_manifest(tmp_path)
    monkeypatch.setattr(
        "github_actions_toolkit.publishing.bash_output",
        ConflictingCommand("npm error You cannot publish over the previously published versions: 0.2.1.\n"),
    )

    NpmRegistry().publish(tmp_path, "0.2.1", {}, False, 0)


def test_npm_publish_swallows_version_conflict_from_legacy_npm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_manifest(tmp_path)
    monkeypatch.setattr(
        "github_actions_toolkit.publishing.bash_output",
        ConflictingCommand("npm ERR! code EPUBLISHCONFLICT\nnpm ERR! cannot publish over existing version\n"),
    )

    NpmRegistry().publish(tmp_path, "0.2.1", {}, False, 0)


def test_npm_publish_rides_through_on_unrelated_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_manifest(tmp_path)
    monkeypatch.setattr(
        "github_actions_toolkit.publishing.bash_output",
        ConflictingCommand("npm error code ENEEDAUTH\nnpm error need auth to publish\n"),
    )

    with pytest.raises(CalledProcessError):
        NpmRegistry().publish(tmp_path, "0.2.1", {}, False, 0)


NUGET_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>netstandard2.1</TargetFramework>
    <SiblingVersion>0.0.0+local</SiblingVersion>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="External.Lib" Version="4.2.0" />
    <PackageReference Include="Org.Sibling" Version="$(SiblingVersion)" />
  </ItemGroup>
</Project>
"""


def write_nuget_project(tmp_path: Path) -> None:
    (tmp_path / "Consumer.csproj").write_text(NUGET_CSPROJ, encoding="utf-8")


def test_nuget_publish_injects_property_flags_beside_the_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_nuget_project(tmp_path)
    recorder = CommandRecorder()
    monkeypatch.setattr("github_actions_toolkit.publishing.bash", recorder)

    NuGetRegistry("key").publish(
        path=tmp_path,
        base_version="1.0.6",
        resolved_dependencies={"Org.Sibling": ResolvedDependency(version="1.0.6", co_publishing=True)},
        dev=False,
        commit_count=0,
    )

    assert recorder.commands[0].startswith("dotnet pack -c Release -p:Version=1.0.6 -p:SiblingVersion=1.0.6 -o ")


def test_nuget_publish_without_dependencies_omits_property_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_nuget_project(tmp_path)
    recorder = CommandRecorder()
    monkeypatch.setattr("github_actions_toolkit.publishing.bash", recorder)

    NuGetRegistry("key").publish(tmp_path, "1.0.6", {}, False, 0)

    assert recorder.commands[0].startswith("dotnet pack -c Release -p:Version=1.0.6 -o ")


def test_nuget_publish_writes_the_nupkg_outside_the_package_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_nuget_project(tmp_path)
    recorder = CommandRecorder()
    monkeypatch.setattr("github_actions_toolkit.publishing.bash", recorder)

    NuGetRegistry("key").publish(tmp_path, "1.0.6", {}, False, 0)

    pack_command, push_command = recorder.commands
    outdir = pack_command.rsplit(" -o ", 1)[1]
    assert not Path(outdir).is_relative_to(tmp_path)
    assert outdir in push_command


def test_nuget_publish_without_matching_reference_is_loud(tmp_path: Path) -> None:
    write_nuget_project(tmp_path)

    with pytest.raises(ValueError, match=r"no PackageReference found for \['Org.Missing'\]"):
        NuGetRegistry("key").publish(
            path=tmp_path,
            base_version="1.0.6",
            resolved_dependencies={"Org.Missing": ResolvedDependency(version="1.0.0", co_publishing=True)},
            dev=False,
            commit_count=0,
        )


def test_nuget_publish_with_literal_version_is_loud(tmp_path: Path) -> None:
    csproj = NUGET_CSPROJ.replace('Version="$(SiblingVersion)"', 'Version="1.0.0"')
    (tmp_path / "Consumer.csproj").write_text(csproj, encoding="utf-8")

    with pytest.raises(ValueError, match=r"carries literal version '1.0.0'"):
        NuGetRegistry("key").publish(
            path=tmp_path,
            base_version="1.0.6",
            resolved_dependencies={"Org.Sibling": ResolvedDependency(version="1.0.6", co_publishing=True)},
            dev=False,
            commit_count=0,
        )


def test_nuget_push_failure_never_leaks_the_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_nuget_project(tmp_path)

    def failing_push(
        command: str,
        *,
        cwd: Path | None = None,
        stdin_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        if "nuget push" in command:
            raise CalledProcessError(
                returncode=1, cmd=command, stderr="Response status code does not indicate success: 401\nsecond line\n"
            )
        return ""

    monkeypatch.setattr("github_actions_toolkit.publishing.bash", failing_push)

    with pytest.raises(SystemExit) as excinfo:
        NuGetRegistry("SECRET-KEY").publish(tmp_path, "1.0.6", {}, False, 0)

    message = str(excinfo.value)
    assert "exit 1" in message
    assert "Response status code does not indicate success: 401" in message
    assert "SECRET-KEY" not in message
    assert "--api-key" not in message


def test_nuget_push_failure_without_stderr_still_names_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_nuget_project(tmp_path)

    def failing_push(
        command: str,
        *,
        cwd: Path | None = None,
        stdin_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        if "nuget push" in command:
            raise CalledProcessError(returncode=2, cmd=command, stderr=None)
        return ""

    monkeypatch.setattr("github_actions_toolkit.publishing.bash", failing_push)

    with pytest.raises(SystemExit, match=r"dotnet nuget push failed \(exit 2\): no stderr output"):
        NuGetRegistry("key").publish(tmp_path, "1.0.6", {}, False, 0)
