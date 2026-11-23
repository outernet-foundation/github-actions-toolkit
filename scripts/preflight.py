# the preflight harness runs uv run --locked scripts/preflight.py in the repo under test
import os

from bashrun.bash import bash, bash_output

runner_temp = os.environ.get("RUNNER_TEMP", "")
if not runner_temp:
    raise SystemExit("preflight runs inside the preflight harness (RUNNER_TEMP is not set)")
bash("uv run --locked preflight-python")
head_sha = bash_output("git rev-parse HEAD").strip()
toolkit_path = f"{runner_temp}/github-actions-toolkit-self-test"
bash(f'git clone "https://github.com/outernet-foundation/github-actions-toolkit.git" "{toolkit_path}"')
bash(f'git -C "{toolkit_path}" checkout "{head_sha}"')
bash(f'uv run --project "{toolkit_path}" --locked --no-dev validate-release-plan')
bash(f'uv run --project "{toolkit_path}" --locked --no-dev gate --dry-run')
bash(
    f'uv run --project "{toolkit_path}" --locked --no-dev gate --dry-run',
    env={"PR_EVENT_ACTION": "synchronize"},
)
bash(f'uv run --project "{toolkit_path}" --locked --no-dev sync-contributor-docs --check')
bash(f'uv run --project "{toolkit_path}" --locked --no-dev generate-github-workflows --check')
bash(
    f'uv run --project "{toolkit_path}" --locked --no-dev retry --dry-run',
    env={"RUN_ID": os.environ.get("GITHUB_RUN_ID", "")},
)
bash(
    f'uv run --project "{toolkit_path}" --locked --no-dev merge-if-ready --dry-run',
    env={"PR_HEAD_SHA": head_sha},
)
