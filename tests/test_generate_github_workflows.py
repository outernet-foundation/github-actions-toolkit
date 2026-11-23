from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml
from bashrun.bash import CalledProcessError, bash_output
from pydantic import TypeAdapter

from github_actions_toolkit.config import PASSES, JobEntry, Pass, PublishConfig, load_config
from github_actions_toolkit.verbs import generate_github_workflows as splicing
from github_actions_toolkit.verbs.generate_github_workflows import (
    SplicedJob,
    SplicedPass,
    StageDocument,
    ToolkitRef,
    YamlMapping,
    acquire_stage,
    parse_stage_document,
    splice_pass,
)
from github_actions_toolkit.verbs.lint_workflows import ensure_zizmor

STR_MAPPING = TypeAdapter(dict[str, object])
JOB_BODIES = TypeAdapter(dict[str, dict[str, object]])


GENERATOR_SHA = "0123456789abcdef0123456789abcdef01234567"
DOMAIN_PIN = "49f1cc649de1d1f53499c85f20be1a5ae49f2be8"
TOOLKIT_CHECKOUT = f"outernet-foundation/github-actions-toolkit/.github/actions/checkout@{GENERATOR_SHA}"
INTEGRATE, RELEASE_DEV, RELEASE_STABLE = PASSES
TOOLKIT = ToolkitRef(sha=GENERATOR_SHA)
SELF = ToolkitRef(sha=None)

BINDINGS = {
    "pr": {"unity-email": "UNITY_EMAIL", "android-keystore": "CI_ANDROID_KEYSTORE"},
    "dev": {"unity-email": "UNITY_EMAIL_DEV", "android-keystore": "CI_ANDROID_KEYSTORE"},
    "stable": {"unity-email": "UNITY_EMAIL", "android-keystore": "ANDROID_KEYSTORE"},
}
UNITY = {"package": "unity-devkit", "repository": "outernet-foundation/unity-devkit", "secrets": BINDINGS}

STAGE = """
name: Build unity

on:
  workflow_call:
    inputs:
      runs-on:
        default: '["ubuntu-latest"]'
      channel:
        default: dev
      free_disk_space:
        type: boolean
        default: false
    secrets:
      unity-email:
        required: true
      android-keystore:
        required: true

env:
  PYTHONUNBUFFERED: "1"

permissions:
  contents: read
  packages: write

jobs:
  plan-builds:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.matrix.outputs.matrix }}
    steps:
      - uses: outernet-foundation/github-actions-toolkit/.github/actions/checkout@DOMAIN_PIN
      - id: matrix
        if: ${{ inputs.free_disk_space }}
        run: uv run --locked matrix
  build:
    needs: [plan-builds]
    runs-on: ${{ fromJSON(inputs.runs-on) }}
    strategy:
      matrix: ${{ fromJson(needs.plan-builds.outputs.matrix) }}
    permissions:
      contents: read
    steps:
      - run: uv run --locked build --channel "$CHANNEL"
        env:
          CHANNEL: ${{ inputs.channel }}
          UNITY_EMAIL: ${{ secrets.unity-email }}
          KEYSTORE: ${{ secrets.android-keystore }}
          PLAN: ${{ needs.plan-builds.outputs.matrix }}
          LABEL: ${{ format('{0}', inputs.channel) }}
""".replace("DOMAIN_PIN", DOMAIN_PIN)


class Recorder:
    def __init__(self, text: str) -> None:
        self.text = text
        self.commands: list[str] = []

    def output(self, command: str) -> str:
        self.commands.append(command)
        return self.text


class Failer:
    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code

    def output(self, command: str) -> str:
        raise CalledProcessError(self.exit_code, command)


def loaded(jobs: Mapping[str, object], tmp_path: Path) -> dict[str, JobEntry]:
    path = tmp_path / "publish.yml"
    path.write_text(yaml.safe_dump({"jobs": jobs}), encoding="utf-8")
    config = load_config(path)
    assert config.jobs is not None
    return config.jobs


def fan(
    jobs: Mapping[str, object],
    stages: dict[str, StageDocument],
    channel_pass: Pass,
    toolkit: ToolkitRef,
    tmp_path: Path,
) -> SplicedPass:
    return splice_pass(loaded(jobs, tmp_path), channel_pass, stages, toolkit)


def unity_fan(jobs: Mapping[str, object], channel_pass: Pass, toolkit: ToolkitRef, tmp_path: Path) -> SplicedPass:
    stage = parse_stage_document(STAGE, "build-unity.yml")
    return fan(jobs, {"build-unity": stage}, channel_pass, toolkit, tmp_path)


def job_of(spliced: SplicedPass, key: str) -> SplicedJob:
    return next(job for job in spliced.jobs if job.key == key)


def body_of(spliced: SplicedPass, key: str) -> YamlMapping:
    return job_of(spliced, key).body


def step_of(body: YamlMapping, index: int) -> YamlMapping:
    steps = body["steps"]
    assert isinstance(steps, list)
    step = steps[index]
    assert isinstance(step, dict)
    return step


def env_of(body: YamlMapping) -> YamlMapping:
    env = step_of(body, 0)["env"]
    assert isinstance(env, dict)
    return env


def installed_wheel(root: Path, stamp: str | None) -> None:
    site_packages = root / ".venv" / "lib" / "python3.13" / "site-packages"
    info = site_packages / "unity_devkit-1.0.dist-info"
    package = site_packages / "unity_devkit"
    info.mkdir(parents=True)
    package.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: unity-devkit\nVersion: 1.0\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    record = ["unity_devkit/__init__.py,,"]
    if stamp is not None:
        (package / "_toolkit_build_commit").write_text(f"{stamp}\n", encoding="utf-8")
        record.append("unity_devkit/_toolkit_build_commit,,")
    (info / "RECORD").write_text("\n".join(record) + "\n", encoding="utf-8")


def test_parse_lifts_the_trigger_under_both_on_spellings() -> None:
    for document in (
        "on:\n  workflow_call:\n    inputs:\n      channel:\n        default: pr\njobs: {a: {}}\n",
        "'on':\n  workflow_call:\n    inputs:\n      channel:\n        default: pr\njobs: {a: {}}\n",
    ):
        stage = parse_stage_document(document, "stage")

        assert stage.workflow_call.inputs["channel"].default == "pr"
        assert "on" not in stage.model_dump()


def test_parse_keeps_string_scalars_apart_from_typed_ones() -> None:
    stage = parse_stage_document(
        "on:\n  workflow_call:\n    inputs:\n      depth:\n        default: 0\njobs:\n  a:\n    runs-on: ubuntu-latest\n",
        "stage",
    )

    assert stage.workflow_call.inputs["depth"].default == 0
    assert not isinstance(stage.workflow_call.inputs["depth"].default, str)


def test_parse_refuses_a_second_trigger() -> None:
    with pytest.raises(SystemExit, match="only trigger"):
        parse_stage_document("on:\n  workflow_call:\n  workflow_dispatch:\njobs: {a: {}}\n", "stage")


def test_parse_refuses_a_stage_without_workflow_call() -> None:
    with pytest.raises(SystemExit, match="only trigger"):
        parse_stage_document("on:\n  push:\njobs: {a: {}}\n", "stage")


def test_parse_refuses_a_stage_concurrency() -> None:
    with pytest.raises(SystemExit, match="concurrency: Extra inputs are not permitted"):
        parse_stage_document("on:\n  workflow_call:\nconcurrency:\n  group: x\njobs: {a: {}}\n", "stage")


def test_parse_refuses_a_document_without_jobs() -> None:
    with pytest.raises(SystemExit, match="jobs: Field required"):
        parse_stage_document("on:\n  workflow_call:\n", "stage")


def test_parse_names_the_file_of_a_malformed_document() -> None:
    with pytest.raises(SystemExit, match=r"stage\.yml: "):
        parse_stage_document("on: [unclosed", "stage.yml")


def test_integrate_keys_lead_with_the_entry(tmp_path: Path) -> None:
    spliced = unity_fan({"build-unity": UNITY}, INTEGRATE, TOOLKIT, tmp_path)

    assert [job.key for job in spliced.jobs] == ["build-unity-plan-builds", "build-unity-build"]


def test_release_keys_lead_with_the_channel(tmp_path: Path) -> None:
    dev = unity_fan({"build-unity": UNITY}, RELEASE_DEV, TOOLKIT, tmp_path)
    stable = unity_fan({"build-unity": UNITY}, RELEASE_STABLE, TOOLKIT, tmp_path)

    assert [job.key for job in dev.jobs] == ["dev-build-unity-plan-builds", "dev-build-unity-build"]
    assert [job.key for job in stable.jobs] == ["stable-build-unity-plan-builds", "stable-build-unity-build"]


def test_internal_needs_take_the_prefix_and_the_tails_are_the_sinks(tmp_path: Path) -> None:
    spliced = unity_fan({"build-unity": UNITY}, RELEASE_DEV, TOOLKIT, tmp_path)

    assert job_of(spliced, "dev-build-unity-plan-builds").needs == ()
    assert job_of(spliced, "dev-build-unity-build").needs == ("dev-build-unity-plan-builds",)
    assert spliced.tails == ("dev-build-unity-build",)


def test_needs_references_in_expressions_take_the_prefix(tmp_path: Path) -> None:
    spliced = unity_fan({"build-unity": UNITY}, INTEGRATE, TOOLKIT, tmp_path)

    assert (
        env_of(body_of(spliced, "build-unity-build"))["PLAN"] == "${{ needs.build-unity-plan-builds.outputs.matrix }}"
    )
    strategy = body_of(spliced, "build-unity-build")["strategy"]
    assert isinstance(strategy, dict)
    assert strategy["matrix"] == "${{ fromJson(needs.build-unity-plan-builds.outputs.matrix) }}"


def test_stage_level_env_folds_into_every_job_and_the_job_wins_per_key(tmp_path: Path) -> None:
    stage = parse_stage_document(
        STAGE.replace(
            "    steps:\n      - run: uv run", "    env:\n      CHANNEL: local\n    steps:\n      - run: uv run"
        ),
        "build-unity.yml",
    )
    spliced = fan({"build-unity": UNITY}, {"build-unity": stage}, INTEGRATE, TOOLKIT, tmp_path)

    plan_env = body_of(spliced, "build-unity-plan-builds")["env"]
    assert plan_env == {"PYTHONUNBUFFERED": "1"}
    assert body_of(spliced, "build-unity-build")["env"] == {"PYTHONUNBUFFERED": "1", "CHANNEL": "local"}


def test_job_permissions_replace_the_stage_level_block(tmp_path: Path) -> None:
    spliced = unity_fan({"build-unity": UNITY}, INTEGRATE, TOOLKIT, tmp_path)

    assert body_of(spliced, "build-unity-plan-builds")["permissions"] == {"contents": "read", "packages": "write"}
    assert body_of(spliced, "build-unity-build")["permissions"] == {"contents": "read"}


def test_inputs_resolve_to_literals_stamped_with_the_channel(tmp_path: Path) -> None:
    for channel_pass, prefix, channel in (
        (INTEGRATE, "", "pr"),
        (RELEASE_DEV, "dev-", "dev"),
        (RELEASE_STABLE, "stable-", "stable"),
    ):
        spliced = unity_fan({"build-unity": UNITY}, channel_pass, TOOLKIT, tmp_path)
        env = env_of(body_of(spliced, f"{prefix}build-unity-build"))

        assert env["CHANNEL"] == channel
        assert env["LABEL"] == "${{ format('{0}', '" + channel + "') }}"


def test_a_whole_span_boolean_input_crosses_as_a_boolean(tmp_path: Path) -> None:
    spliced = unity_fan({"build-unity": UNITY}, INTEGRATE, TOOLKIT, tmp_path)

    assert step_of(body_of(spliced, "build-unity-plan-builds"), 1)["if"] is False


def test_an_input_with_no_declared_default_is_red(tmp_path: Path) -> None:
    stage = parse_stage_document(
        STAGE.replace(
            "      free_disk_space:\n        type: boolean\n        default: false\n",
            "      free_disk_space:\n        type: boolean\n        required: true\n",
        ),
        "build-unity.yml",
    )

    with pytest.raises(SystemExit, match="input 'free_disk_space' is referenced with no declared default"):
        fan({"build-unity": UNITY}, {"build-unity": stage}, INTEGRATE, TOOLKIT, tmp_path)


def test_secrets_bind_to_the_pass_channel(tmp_path: Path) -> None:
    pr = env_of(body_of(unity_fan({"build-unity": UNITY}, INTEGRATE, TOOLKIT, tmp_path), "build-unity-build"))
    dev = env_of(body_of(unity_fan({"build-unity": UNITY}, RELEASE_DEV, TOOLKIT, tmp_path), "dev-build-unity-build"))
    stable = env_of(
        body_of(unity_fan({"build-unity": UNITY}, RELEASE_STABLE, TOOLKIT, tmp_path), "stable-build-unity-build")
    )

    assert pr["UNITY_EMAIL"] == "${{ secrets.UNITY_EMAIL }}"
    assert pr["KEYSTORE"] == "${{ secrets.CI_ANDROID_KEYSTORE }}"
    assert dev["UNITY_EMAIL"] == "${{ secrets.UNITY_EMAIL_DEV }}"
    assert stable["KEYSTORE"] == "${{ secrets.ANDROID_KEYSTORE }}"


def test_a_referenced_slot_with_no_binding_is_red(tmp_path: Path) -> None:
    bindings = {channel: maps for channel, maps in BINDINGS.items() if channel != "pr"}
    entry = {"package": "unity-devkit", "repository": "outernet-foundation/unity-devkit", "secrets": bindings}

    with pytest.raises(SystemExit, match="secret slot 'unity-email' has no pr binding"):
        unity_fan({"build-unity": entry}, INTEGRATE, TOOLKIT, tmp_path)


def test_a_binding_naming_an_undeclared_slot_is_red(tmp_path: Path) -> None:
    bindings = {**BINDINGS, "pr": {**BINDINGS["pr"], "android-key-alias": "CI_ANDROID_KEY_ALIAS"}}
    entry = {"package": "unity-devkit", "repository": "outernet-foundation/unity-devkit", "secrets": bindings}

    with pytest.raises(SystemExit, match="'android-key-alias'"):
        unity_fan({"build-unity": entry}, INTEGRATE, TOOLKIT, tmp_path)


def test_a_binding_typo_under_an_untargeted_channel_is_red(tmp_path: Path) -> None:
    bindings = {**BINDINGS, "stable": {**BINDINGS["stable"], "unity-serial": "UNITY_SERIAL"}}
    entry = {
        "package": "unity-devkit",
        "repository": "outernet-foundation/unity-devkit",
        "secrets": bindings,
        "targets": ["integrate"],
    }

    with pytest.raises(SystemExit, match="does not declare"):
        unity_fan({"build-unity": entry}, INTEGRATE, TOOLKIT, tmp_path)


def test_runners_override_the_runs_on_input_shape(tmp_path: Path) -> None:
    entry = {**UNITY, "runners": ["self-hosted", "unity"]}

    overridden = body_of(unity_fan({"build-unity": entry}, INTEGRATE, TOOLKIT, tmp_path), "build-unity-build")
    defaulted = body_of(unity_fan({"build-unity": UNITY}, INTEGRATE, TOOLKIT, tmp_path), "build-unity-build")

    assert overridden["runs-on"] == ["self-hosted", "unity"]
    assert defaulted["runs-on"] == ["ubuntu-latest"]
    assert (
        body_of(unity_fan({"build-unity": UNITY}, INTEGRATE, TOOLKIT, tmp_path), "build-unity-plan-builds")["runs-on"]
        == "ubuntu-latest"
    )


def test_runners_on_a_stage_without_the_runs_on_shape_is_red(tmp_path: Path) -> None:
    stage = parse_stage_document(
        STAGE.replace("runs-on: ${{ fromJSON(inputs.runs-on) }}", "runs-on: ubuntu-latest"), "build-unity.yml"
    )
    entry = {**UNITY, "runners": ["self-hosted", "unity"]}

    with pytest.raises(SystemExit, match="takes no runs-on input"):
        fan({"build-unity": entry}, {"build-unity": stage}, INTEGRATE, TOOLKIT, tmp_path)


def test_toolkit_refs_take_the_generator_pin(tmp_path: Path) -> None:
    spliced = unity_fan({"build-unity": UNITY}, INTEGRATE, TOOLKIT, tmp_path)

    assert step_of(body_of(spliced, "build-unity-plan-builds"), 0)["uses"] == TOOLKIT_CHECKOUT


def test_toolkit_refs_take_the_self_repository_spelling(tmp_path: Path) -> None:
    spliced = unity_fan({"build-unity": UNITY}, INTEGRATE, SELF, tmp_path)

    assert step_of(body_of(spliced, "build-unity-plan-builds"), 0)["uses"] == "$/.github/actions/checkout"


def test_foreign_uses_refs_pass_through(tmp_path: Path) -> None:
    document = "on:\n  workflow_call:\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09\n"
    entry = {"path": True, "file": ".github/stages/check.yml"}

    spliced = fan(
        {"openapi-drift": entry},
        {"openapi-drift": parse_stage_document(document, "check.yml")},
        INTEGRATE,
        TOOLKIT,
        tmp_path,
    )

    assert (
        step_of(body_of(spliced, "openapi-drift-check"), 0)["uses"]
        == "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09"
    )


def test_needs_naming_a_job_outside_the_stage_is_red(tmp_path: Path) -> None:
    stage = parse_stage_document(STAGE.replace("needs: [plan-builds]", "needs: [gate]"), "build-unity.yml")

    with pytest.raises(SystemExit, match="needs names jobs outside the stage"):
        fan({"build-unity": UNITY}, {"build-unity": stage}, INTEGRATE, TOOLKIT, tmp_path)


def test_a_needs_reference_naming_no_stage_job_is_red(tmp_path: Path) -> None:
    stage = parse_stage_document(
        STAGE.replace(
            "needs.plan-builds.outputs.matrix }}\n          LABEL", "needs.gate.outputs.mode }}\n          LABEL"
        ),
        "build-unity.yml",
    )

    with pytest.raises(SystemExit, match="names no job in the stage"):
        fan({"build-unity": UNITY}, {"build-unity": stage}, INTEGRATE, TOOLKIT, tmp_path)


def test_an_expression_that_cannot_be_read_is_red(tmp_path: Path) -> None:
    stage = parse_stage_document(
        STAGE.replace("LABEL: ${{ format('{0}', inputs.channel) }}", "LABEL: ${{ x == 'a }}"), "build-unity.yml"
    )

    with pytest.raises(SystemExit, match="expression cannot be read"):
        fan({"build-unity": UNITY}, {"build-unity": stage}, INTEGRATE, TOOLKIT, tmp_path)


def test_a_uses_entry_splices_as_one_job_with_the_generator_pin(tmp_path: Path) -> None:
    entry = {
        "uses": "outernet-foundation/github-actions-toolkit/.github/workflows/mirror.yml@49f1cc649de1d1f53499c85f20be1a5ae49f2be8"
    }

    spliced = fan({"mirror": entry}, {}, INTEGRATE, TOOLKIT, tmp_path)

    assert [(job.key, job.needs, job.body) for job in spliced.jobs] == [
        (
            "mirror",
            (),
            {"uses": f"outernet-foundation/github-actions-toolkit/.github/workflows/mirror.yml@{GENERATOR_SHA}"},
        )
    ]
    assert spliced.tails == ("mirror",)


def test_targets_select_the_passes_an_entry_splices_into(tmp_path: Path) -> None:
    entry = {**UNITY, "targets": ["integrate"]}
    stage = {"build-unity": parse_stage_document(STAGE, "build-unity.yml")}

    assert [job.key for job in fan({"build-unity": entry}, stage, INTEGRATE, TOOLKIT, tmp_path).jobs]
    assert fan({"build-unity": entry}, stage, RELEASE_DEV, TOOLKIT, tmp_path) == SplicedPass(jobs=(), tails=())


def test_fetch_domain_stage_pins_the_url_at_the_wheel_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed_wheel(tmp_path, DOMAIN_PIN)
    fetched = Recorder("stage body")
    monkeypatch.setattr(splicing, "bash_output", fetched.output)

    stage = splicing.fetch_domain_stage(
        "unity-devkit", "owner/repo", Path(".github/workflows/build-unity.yml"), tmp_path
    )

    assert stage == "stage body"
    assert fetched.commands == [
        f'curl -fsSL "https://raw.githubusercontent.com/owner/repo/{DOMAIN_PIN}/.github/workflows/build-unity.yml"'
    ]


def test_fetch_domain_stage_normalizes_the_distribution_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed_wheel(tmp_path, DOMAIN_PIN)
    monkeypatch.setattr(splicing, "bash_output", Recorder("stage body").output)

    stage = splicing.fetch_domain_stage(
        "unity_devkit", "owner/repo", Path(".github/workflows/build-unity.yml"), tmp_path
    )

    assert stage == "stage body"


def test_fetch_domain_stage_refuses_an_uninstalled_package(tmp_path: Path) -> None:
    installed_wheel(tmp_path, DOMAIN_PIN)

    with pytest.raises(SystemExit, match="other-devkit: not installed"):
        splicing.fetch_domain_stage("other-devkit", "owner/repo", Path(".github/workflows/build-unity.yml"), tmp_path)


def test_fetch_domain_stage_refuses_a_wheel_without_a_stamp(tmp_path: Path) -> None:
    installed_wheel(tmp_path, None)

    with pytest.raises(SystemExit, match="carries no commit stamp"):
        splicing.fetch_domain_stage("unity-devkit", "owner/repo", Path(".github/workflows/build-unity.yml"), tmp_path)


def test_fetch_domain_stage_refuses_a_stamp_that_is_not_a_commit_sha(tmp_path: Path) -> None:
    installed_wheel(tmp_path, "v1.2.3")

    with pytest.raises(SystemExit, match="not a full commit sha"):
        splicing.fetch_domain_stage("unity-devkit", "owner/repo", Path(".github/workflows/build-unity.yml"), tmp_path)


def test_fetch_domain_stage_refuses_an_ambiguous_venv(tmp_path: Path) -> None:
    installed_wheel(tmp_path, DOMAIN_PIN)
    (tmp_path / ".venv" / "lib" / "python3.12" / "site-packages").mkdir(parents=True)

    with pytest.raises(SystemExit, match="exactly one python site-packages"):
        splicing.fetch_domain_stage("unity-devkit", "owner/repo", Path(".github/workflows/build-unity.yml"), tmp_path)


def test_acquire_stage_reads_a_local_stage_under_the_stage_directory(tmp_path: Path) -> None:
    stage = "on:\n  workflow_call:\njobs:\n  check:\n    runs-on: ubuntu-latest\n"
    (tmp_path / ".github" / "stages").mkdir(parents=True)
    (tmp_path / ".github" / "stages" / "openapi-drift.yml").write_text(stage, encoding="utf-8")
    entry = loaded({"openapi-drift": {"path": True}}, tmp_path)["openapi-drift"]

    assert list(acquire_stage(entry, "openapi-drift", tmp_path).jobs) == ["check"]


def test_acquire_stage_names_a_missing_local_stage(tmp_path: Path) -> None:
    entry = loaded({"openapi-drift": {"path": True}}, tmp_path)["openapi-drift"]

    with pytest.raises(SystemExit, match=r"\.github/stages/openapi-drift\.yml: stage file not found"):
        acquire_stage(entry, "openapi-drift", tmp_path)


def test_acquire_stage_fetches_a_domain_stage_at_the_wheel_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_wheel(tmp_path, DOMAIN_PIN)
    recorder = Recorder(STAGE)
    monkeypatch.setattr(splicing, "bash_output", recorder.output)
    entry = loaded({"build-unity": UNITY}, tmp_path)["build-unity"]

    stage = acquire_stage(entry, "build-unity", tmp_path)

    expected_url = f"https://raw.githubusercontent.com/outernet-foundation/unity-devkit/{DOMAIN_PIN}/.github/workflows/build-unity.yml"
    assert recorder.commands == [f'curl -fsSL "{expected_url}"']
    assert list(stage.jobs) == ["plan-builds", "build"]


def test_acquire_stage_names_a_failed_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed_wheel(tmp_path, DOMAIN_PIN)
    monkeypatch.setattr(splicing, "bash_output", Failer(exit_code=22).output)
    entry = loaded({"build-unity": UNITY}, tmp_path)["build-unity"]

    with pytest.raises(SystemExit, match=r"could not fetch the stage .*exit 22"):
        acquire_stage(entry, "build-unity", tmp_path)


def test_config_round_trips_a_uses_entry(tmp_path: Path) -> None:
    path = tmp_path / "publish.yml"
    path.write_text(
        "jobs:\n  mirror:\n    uses: outernet-foundation/github-actions-toolkit/.github/workflows/mirror.yml@49f1cc649de1d1f53499c85f20be1a5ae49f2be8\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert isinstance(config, PublishConfig)
    assert config.jobs is not None
    assert config.jobs["mirror"].uses is not None


MIRROR_PIN = "49f1cc649de1d1f53499c85f20be1a5ae49f2be8"
MIRROR_USES = f"outernet-foundation/github-actions-toolkit/.github/workflows/mirror.yml@{MIRROR_PIN}"
TOOLKIT_REMOTE = "git@github.com:outernet-foundation/github-actions-toolkit.git"
CONSUMER_REMOTE = "https://github.com/outernet-foundation/placeframe-capture-tool"
GOLDEN = Path(__file__).resolve().parent / "golden"

GOLDEN_STAGE = """
name: Build unity

on:
  workflow_call:
    inputs:
      runs-on:
        default: '["ubuntu-latest"]'
    secrets:
      unity-email:
        required: true

permissions:
  contents: read
  packages: write

jobs:
  plan-builds:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.matrix.outputs.matrix }}
    steps:
      - uses: outernet-foundation/github-actions-toolkit/.github/actions/checkout@DOMAIN_PIN
      - id: matrix
        run: uv run --locked matrix
  build:
    needs: [plan-builds]
    runs-on: ${{ fromJSON(inputs.runs-on) }}
    if: ${{ github.repository != 'example/excluded' }}
    steps:
      - run: uv run --locked build --channel "$CHANNEL"
        env:
          CHANNEL: ${{ inputs.channel }}
          UNITY_EMAIL: ${{ secrets.unity-email }}
""".replace("DOMAIN_PIN", DOMAIN_PIN)

DRIFT_STAGE = """
on:
  workflow_call:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: outernet-foundation/github-actions-toolkit/.github/actions/toolkit-checkout@DOMAIN_PIN
      - uses: outernet-foundation/github-actions-toolkit/.github/actions/setup-uv@DOMAIN_PIN
      - run: uv run --locked openapi-client-codegen --config openapi-client-codegen.yaml --check
""".replace("DOMAIN_PIN", DOMAIN_PIN)

GOLDEN_JOBS = {
    "mirror": {"uses": MIRROR_USES},
    "build-unity": {
        "path": True,
        "runners": ["self-hosted", "unity"],
        "secrets": {channel: {"unity-email": "UNITY_EMAIL"} for channel in ("pr", "dev", "stable")},
    },
    "openapi-drift": {"path": True},
}


class Shell:
    def __init__(self, outputs: dict[str, str]) -> None:
        self.outputs = outputs

    def output(self, command: str, *, cwd: Path | None = None) -> str:
        if command not in self.outputs:
            raise CalledProcessError(128, command)
        return self.outputs[command]


def faked_shell(monkeypatch: pytest.MonkeyPatch, remote: str) -> None:
    monkeypatch.setattr(
        splicing,
        "bash_output",
        Shell({"git remote get-url origin": remote, "git rev-parse HEAD": GENERATOR_SHA}).output,
    )


def golden_consumer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, remote: str = CONSUMER_REMOTE) -> Path:
    stages = tmp_path / ".github" / "stages"
    stages.mkdir(parents=True, exist_ok=True)
    (stages / "build-unity.yml").write_text(GOLDEN_STAGE, encoding="utf-8")
    (stages / "openapi-drift.yml").write_text(DRIFT_STAGE, encoding="utf-8")
    faked_shell(monkeypatch, remote)
    config_path = tmp_path / "publish.yml"
    config_path.write_text(yaml.safe_dump({"jobs": GOLDEN_JOBS}, sort_keys=False), encoding="utf-8")
    return config_path


def golden_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, remote: str = CONSUMER_REMOTE) -> dict[Path, str]:
    config_path = golden_consumer(monkeypatch, tmp_path, remote=remote)
    splicing.main(config=config_path)
    workflows_directory = tmp_path / ".github" / "workflows"
    return {
        path.relative_to(tmp_path): path.read_text(encoding="utf-8") for path in sorted(workflows_directory.iterdir())
    }


def workflows(tmp_path: Path) -> list[str]:
    return sorted(path.name for path in (tmp_path / ".github" / "workflows").iterdir())


def parsed(text: str) -> dict[str, object]:
    return STR_MAPPING.validate_python(yaml.safe_load(text))


def document_jobs(text: str) -> dict[str, dict[str, object]]:
    return JOB_BODIES.validate_python(parsed(text)["jobs"])


def golden(name: str, text: str) -> None:
    path = GOLDEN / name
    if os.environ.get("WRITE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert text == path.read_text(encoding="utf-8"), f"{name} drifted from the committed golden"


def test_write_mode_writes_the_five_consumer_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = golden_consumer(monkeypatch, tmp_path)

    splicing.main(config=config_path)

    assert workflows(tmp_path) == [
        "cleanup-pr-releases.yml",
        "integrate.yml",
        "preflight.yml",
        "release.yml",
        "retry.yml",
    ]


def test_self_mode_writes_the_four_underscore_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = golden_consumer(monkeypatch, tmp_path, remote=TOOLKIT_REMOTE)

    splicing.main(config=config_path)

    assert workflows(tmp_path) == ["_cleanup-pr-releases.yml", "_integrate.yml", "_preflight.yml", "_retry.yml"]
    integrate = (tmp_path / ".github" / "workflows" / "_integrate.yml").read_text(encoding="utf-8")
    assert "uses: $/.github/workflows/gate.yml" in integrate
    assert "retry-workflow: _retry.yml" in integrate


def test_check_mode_passes_over_committed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = golden_consumer(monkeypatch, tmp_path)
    splicing.main(config=config_path)

    splicing.main(check=True, config=config_path)

    assert "match the committed files" in capsys.readouterr().out


def test_check_mode_fails_on_a_drifted_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = golden_consumer(monkeypatch, tmp_path)
    splicing.main(config=config_path)
    drifted = tmp_path / ".github" / "workflows" / "integrate.yml"
    drifted.write_text(drifted.read_text(encoding="utf-8") + "#drift\n", encoding="utf-8")

    with pytest.raises(SystemExit, match=r"integrate\.yml\): run generate-github-workflows"):
        splicing.main(check=True, config=config_path)


def test_a_config_without_jobs_prints_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    faked_shell(monkeypatch, CONSUMER_REMOTE)
    config_path = tmp_path / "publish.yml"
    config_path.write_text("", encoding="utf-8")

    splicing.main(check=True, config=config_path)

    assert "no jobs" in capsys.readouterr().out
    assert not (tmp_path / ".github").exists()


def test_a_bare_jobs_key_adopts_with_an_empty_fan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    faked_shell(monkeypatch, CONSUMER_REMOTE)
    config_path = tmp_path / "publish.yml"
    config_path.write_text("jobs:\n", encoding="utf-8")

    splicing.main(config=config_path)

    integrate = (tmp_path / ".github" / "workflows" / "integrate.yml").read_text(encoding="utf-8")
    assert "needs: [gate]" in integrate
    release = (tmp_path / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "needs:" not in release


def test_the_lane_wakes_spell_ready_for_review_and_the_four_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = golden_files(monkeypatch, tmp_path)

    types = parsed(files[Path(".github/workflows/integrate.yml")])["on"]
    assert types == {
        "pull_request_target": {
            "branches": ["dev"],
            "types": ["labeled", "synchronize", "reopened", "ready_for_review"],
        }
    }


def test_the_lane_files_carry_the_zizmor_ignore_at_the_on_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = golden_files(monkeypatch, tmp_path)

    for name in (".github/workflows/integrate.yml", ".github/workflows/cleanup-pr-releases.yml"):
        line = next(line for line in files[Path(name)].splitlines() if line.startswith("'on':"))
        assert "zizmor: ignore[dangerous-triggers]" in line


def test_the_tier_one_wakes_are_opened_and_synchronize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = golden_files(monkeypatch, tmp_path)

    types = parsed(files[Path(".github/workflows/preflight.yml")])["on"]
    assert types == {"pull_request": {"branches": ["dev"], "types": ["opened", "synchronize"]}}


def test_the_fan_jobs_need_the_spine_and_the_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = golden_files(monkeypatch, tmp_path)

    drift = document_jobs(files[Path(".github/workflows/integrate.yml")])["openapi-drift-check"]
    assert drift["needs"] == ["gate", "preflight", "mirror"]
    assert drift["if"] == "${{ needs.gate.outputs.mode == 'full' }}"


def test_the_stage_if_folds_into_the_pass_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = golden_files(monkeypatch, tmp_path)

    build = document_jobs(files[Path(".github/workflows/release.yml")])["dev-build-unity-build"]
    assert build["if"] == "${{ github.ref == 'refs/heads/dev' && (github.repository != 'example/excluded') }}"


def test_the_delivery_jobs_gate_on_the_branch_and_wait_on_the_tails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = golden_files(monkeypatch, tmp_path)

    jobs = document_jobs(files[Path(".github/workflows/release.yml")])
    assert jobs["prerelease"]["needs"] == ["dev-mirror", "dev-build-unity-build", "dev-openapi-drift-check"]
    assert jobs["release"]["needs"] == ["stable-mirror", "stable-build-unity-build", "stable-openapi-drift-check"]
    assert jobs["prerelease"]["if"] == "${{ !cancelled() && !failure() && github.ref == 'refs/heads/dev' }}"


def test_a_false_consumer_script_stamps_the_with_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = golden_files(monkeypatch, tmp_path)
    integrate = files[Path(".github/workflows/integrate.yml")]
    assert "consumer-script: false" not in integrate

    config_path = golden_consumer(monkeypatch, tmp_path)
    config_path.write_text(config_path.read_text(encoding="utf-8") + "consumer-script: false\n", encoding="utf-8")
    splicing.main(config=config_path)

    integrate = (tmp_path / ".github" / "workflows" / "integrate.yml").read_text(encoding="utf-8")
    assert "    with:\n      consumer-script: false" in integrate


def test_a_false_consumer_script_drops_the_python_steps_from_tier_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = golden_consumer(monkeypatch, tmp_path)
    config_path.write_text(config_path.read_text(encoding="utf-8") + "consumer-script: false\n", encoding="utf-8")
    splicing.main(config=config_path)

    preflight = (tmp_path / ".github" / "workflows" / "preflight.yml").read_text(encoding="utf-8")
    assert "uv sync --locked" not in preflight
    assert "scripts/preflight.py" not in preflight
    assert "generate-github-workflows --check" in preflight


def test_an_entry_key_colliding_with_the_spine_is_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    faked_shell(monkeypatch, CONSUMER_REMOTE)
    config_path = tmp_path / "publish.yml"
    config_path.write_text(yaml.safe_dump({"jobs": {"gate": {"uses": MIRROR_USES}}}, sort_keys=False), encoding="utf-8")

    with pytest.raises(SystemExit, match="job keys twice: \\['gate'\\]"):
        splicing.main(config=config_path)


def test_two_generations_are_byte_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert golden_files(monkeypatch, tmp_path) == golden_files(monkeypatch, tmp_path)


def test_each_remote_spelling_resolves_to_a_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for url, resolves in (
        ("git@github.com:outernet-foundation/boatyard.git", False),
        ("https://gitlab.com/outernet-foundation/github-actions-toolkit.git", False),
        ("git@github.com:outernet-foundation", False),
    ):
        monkeypatch.setattr(splicing, "bash_output", Shell({"git remote get-url origin": url}).output)

        assert splicing.self_repository(tmp_path) is resolves


def test_self_repository_reads_the_origin_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for remote, expected in (
        (CONSUMER_REMOTE, False),
        (TOOLKIT_REMOTE, True),
        ("https://github.com/outernet-foundation/github-actions-toolkit", True),
    ):
        monkeypatch.setattr(splicing, "bash_output", Shell({"git remote get-url origin": remote}).output)

        assert splicing.self_repository(tmp_path) is expected


def test_self_repository_names_a_repo_without_an_origin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(splicing, "bash_output", Shell({}).output)

    with pytest.raises(SystemExit, match="no origin remote"):
        splicing.self_repository(tmp_path)


def test_the_consumer_golden_files_are_byte_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = golden_files(monkeypatch, tmp_path)

    for path, text in files.items():
        golden(f"consumer/{path.name}", text)


def test_the_self_golden_files_are_byte_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = golden_files(monkeypatch, tmp_path, remote=TOOLKIT_REMOTE)

    for path, text in files.items():
        golden(f"self/{path.name}", text)


def test_zizmor_finds_nothing_across_the_golden_files(tmp_path: Path) -> None:
    workflows_directory = tmp_path / ".github" / "workflows"
    workflows_directory.mkdir(parents=True)
    for mode in (GOLDEN / "consumer", GOLDEN / "self"):
        for path in sorted(mode.glob("*.yml")):
            (workflows_directory / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    binary = ensure_zizmor()
    summary = bash_output(f'"{binary}" --offline --format plain --no-progress "{workflows_directory}"')

    # Prove the ignores hold, because a broken inline dangerous-triggers ignore turns the exit red
    assert "No findings to report" in summary
