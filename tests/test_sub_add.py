# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops/commands/submodules/add.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.submodules.add import main

URL = "git@github.com:testowner/myrepo.git"
BRANCH = "16.0"
# These match desired_path(URL, prefix=".third-party") and desired_path(URL)
SUB_PATH_STR = ".third-party/testowner/myrepo"
SUB_NAME = "testowner/myrepo"


def _make_config(force_scheme=None, current_path=".third-party"):
    cfg = MagicMock()
    cfg.submodules.force_scheme = force_scheme
    cfg.submodules.current_path = current_path
    return cfg


def _make_repo():
    return MagicMock()


def _base_patches(tmp_path, mock_repo=None):
    """Return a dict of patches that make the happy path work."""
    if mock_repo is None:
        mock_repo = _make_repo()
    mock_repo.index.diff.return_value = [MagicMock()]
    mock_repo.index.commit.return_value = MagicMock(hexsha="ab" * 8)
    return {
        "oops.commands.submodules.add.config": _make_config(),
        "oops.commands.submodules.add.get_local_repo": MagicMock(return_value=(mock_repo, tmp_path)),
        "oops.commands.submodules.add.read_gitmodules": MagicMock(return_value=MagicMock()),
        "oops.commands.submodules.add.commit": MagicMock(),
    }


def _invoke(tmp_path, args=None, extra_patches=None):
    """Invoke `oops submodules add` with standard mocks; return (result, patches)."""
    patches = _base_patches(tmp_path)
    if extra_patches:
        patches.update(extra_patches)
    with _apply_patches(patches):
        result = CliRunner().invoke(main, args or [URL, BRANCH, "-y"])
    return result, patches


class _apply_patches:
    """Context manager that applies a dict of {target: mock_or_value} patches."""

    def __init__(self, patches):
        self._patches = patches
        self._patcher_stack = []

    def __enter__(self):
        for target, mock in self._patches.items():
            if isinstance(mock, MagicMock):
                p = patch(target, mock)
            else:
                p = patch(target, mock)
            p.start()
            self._patcher_stack.append(p)
        return self

    def __exit__(self, *_args):
        for p in reversed(self._patcher_stack):
            p.stop()


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_exits_cleanly(self, tmp_path):
        # click.Abort() produces exit code 1; that is expected for a dry run
        result, _ = _invoke(tmp_path, args=[URL, BRANCH, "-y", "--dry-run"])
        assert result.exit_code == 1

    def test_dry_run_prints_warning(self, tmp_path):
        result, _ = _invoke(tmp_path, args=[URL, BRANCH, "-y", "--dry-run"])
        assert "dry run" in result.output.lower()

    def test_dry_run_does_not_commit(self, tmp_path):
        _, patches = _invoke(tmp_path, args=[URL, BRANCH, "-y", "--dry-run"])
        patches["oops.commands.submodules.add.commit"].assert_not_called()


# ---------------------------------------------------------------------------
# Guard checks
# ---------------------------------------------------------------------------


class TestGuards:
    def test_existing_destination_exits_error(self, tmp_path):
        sub_path = tmp_path / SUB_PATH_STR
        sub_path.mkdir(parents=True)
        result, _ = _invoke(tmp_path)
        assert result.exit_code != 0

    def test_existing_destination_prints_error_message(self, tmp_path):
        sub_path = tmp_path / SUB_PATH_STR
        sub_path.mkdir(parents=True)
        result, _ = _invoke(tmp_path)
        assert "already exists" in result.output

    def test_stale_git_modules_dir_exits_error(self, tmp_path):
        stale = tmp_path / ".git" / "modules" / SUB_NAME
        stale.mkdir(parents=True)
        result, _ = _invoke(tmp_path)
        assert result.exit_code != 0

    def test_stale_git_modules_dir_prints_error_message(self, tmp_path):
        stale = tmp_path / ".git" / "modules" / SUB_NAME
        stale.mkdir(parents=True)
        result, _ = _invoke(tmp_path)
        assert "already exists" in result.output


# ---------------------------------------------------------------------------
# Staging — regression tests for the fix
# ---------------------------------------------------------------------------


class TestStaging:
    def test_submodule_dir_not_in_staged_files(self, tmp_path):
        """Regression: the submodule directory must not be explicitly staged.

        git submodule add already stages it; double-staging with an absolute path
        that commit() would re-resolve caused path errors before the fix.
        """
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        commit_mock = patches["oops.commands.submodules.add.commit"]
        commit_mock.assert_called_once()
        staged = commit_mock.call_args[0][2]  # third positional arg: files list
        assert not any(SUB_PATH_STR in p for p in staged)

    def test_gitmodules_is_staged(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        commit_mock = patches["oops.commands.submodules.add.commit"]
        staged = commit_mock.call_args[0][2]
        assert any(".gitmodules" in p for p in staged)

    def test_staged_paths_are_absolute(self, tmp_path):
        """Regression: all paths passed to commit() must be absolute."""
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        commit_mock = patches["oops.commands.submodules.add.commit"]
        staged = commit_mock.call_args[0][2]
        assert all(Path(p).is_absolute() for p in staged), f"Non-absolute path in {staged}"

    def test_commit_called_with_submodule_add_message(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        commit_mock = patches["oops.commands.submodules.add.commit"]
        message_name = commit_mock.call_args[0][3]
        assert message_name == "submodule_add"


# ---------------------------------------------------------------------------
# --no-commit
# ---------------------------------------------------------------------------


class TestNoCommit:
    def test_no_commit_skips_commit_call(self, tmp_path):
        result, patches = _invoke(tmp_path, args=[URL, BRANCH, "-y", "--no-commit"])
        assert result.exit_code == 0, result.output
        patches["oops.commands.submodules.add.commit"].assert_not_called()

    def test_no_commit_stages_via_index_add(self, tmp_path):
        mock_repo = _make_repo()
        patches = _base_patches(tmp_path, mock_repo=mock_repo)
        with _apply_patches(patches):
            result = CliRunner().invoke(main, [URL, BRANCH, "-y", "--no-commit"])
        assert result.exit_code == 0, result.output
        mock_repo.index.add.assert_called_once()

    def test_no_commit_index_add_uses_absolute_paths(self, tmp_path):
        mock_repo = _make_repo()
        patches = _base_patches(tmp_path, mock_repo=mock_repo)
        with _apply_patches(patches):
            result = CliRunner().invoke(main, [URL, BRANCH, "-y", "--no-commit"])
        assert result.exit_code == 0, result.output
        staged = mock_repo.index.add.call_args[0][0]
        assert all(Path(p).is_absolute() for p in staged), f"Non-absolute path in {staged}"


# ---------------------------------------------------------------------------
# Symlinks
# ---------------------------------------------------------------------------


class TestSymlinks:
    def test_symlink_paths_staged_alongside_gitmodules(self, tmp_path):
        mock_repo = _make_repo()
        mock_repo.index.diff.return_value = [MagicMock()]
        mock_repo.index.commit.return_value = MagicMock(hexsha="ab" * 8)
        commit_mock = MagicMock()
        patches = {
            "oops.commands.submodules.add.config": _make_config(),
            "oops.commands.submodules.add.get_local_repo": MagicMock(
                return_value=(mock_repo, tmp_path)
            ),
            "oops.commands.submodules.add.read_gitmodules": MagicMock(return_value=MagicMock()),
            "oops.commands.submodules.add.commit": commit_mock,
            "oops.commands.submodules.add.find_addon_dirs": MagicMock(
                return_value=[tmp_path / SUB_PATH_STR / "my_addon"]
            ),
            "oops.commands.submodules.add.create_symlink": MagicMock(return_value="my_addon"),
        }
        with _apply_patches(patches):
            result = CliRunner().invoke(main, [URL, BRANCH, "-y", "--auto-symlinks"])

        assert result.exit_code == 0, result.output
        staged = commit_mock.call_args[0][2]
        assert any("my_addon" in p for p in staged)
        assert any(".gitmodules" in p for p in staged)
