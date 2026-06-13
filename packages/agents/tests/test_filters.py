from pathlib import Path

from devmanager_agents.filters import is_worth_reviewing


def test_filter_rejects_binary_file(tmp_path: Path):
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n" + b"\x00" * 1000)
    assert (
        is_worth_reviewing(
            file_path="logo.png",
            repo_dir=tmp_path,
            is_binary=True,
            is_generated=False,
            is_vendor=False,
            added_lines=1,
            deleted_lines=0,
            language="image",
        )
        is False
    )


def test_filter_rejects_oversized_file(tmp_path: Path):
    (tmp_path / "huge.json").write_text("x" * 60_000)
    assert (
        is_worth_reviewing(
            file_path="huge.json",
            repo_dir=tmp_path,
            is_binary=False,
            is_generated=False,
            is_vendor=False,
            added_lines=2000,
            deleted_lines=0,
            language="json",
        )
        is False
    )


def test_filter_rejects_trivial_change(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n")
    assert (
        is_worth_reviewing(
            file_path="a.py",
            repo_dir=tmp_path,
            is_binary=False,
            is_generated=False,
            is_vendor=False,
            added_lines=1,
            deleted_lines=1,
            language="python",
        )
        is False
    )


def test_filter_accepts_real_code(tmp_path: Path):
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    assert (
        is_worth_reviewing(
            file_path="a.py",
            repo_dir=tmp_path,
            is_binary=False,
            is_generated=False,
            is_vendor=False,
            added_lines=5,
            deleted_lines=0,
            language="python",
        )
        is True
    )
