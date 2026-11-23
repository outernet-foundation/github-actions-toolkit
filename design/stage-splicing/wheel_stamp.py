from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

COMMIT_STAMP_NAME = "_toolkit_build_commit"


@contextmanager
def ephemeral_commit_stamp(package_path: Path, import_name: str, commit_sha: str) -> Generator[None]:
    # Place the stamp inside the import package, because the wheel ships it by default and packages cannot collide
    stamp_path = package_path / "src" / import_name / COMMIT_STAMP_NAME
    existed = stamp_path.exists()
    original = stamp_path.read_text(encoding="utf-8") if existed else None
    try:
        stamp_path.write_text(commit_sha + "\n", encoding="utf-8")
        yield
    finally:
        if existed:
            stamp_path.write_text(original, encoding="utf-8")
        if not existed:
            stamp_path.unlink()


def stamp_in_publish_loop(package_path: Path, import_name: str, commit_sha: str) -> None:
    # Share the per-package loop's ephemeral window, so the wheel records the commit and the tree restores after
    with ephemeral_commit_stamp(package_path, import_name, commit_sha):
        pass
