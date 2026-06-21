# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops/commands/submodules/add.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.submodules.add import main

URL = "git@github.com:testowner/myrepo.git"
BRANCH = "16.0"
# These match desired_path(URL, prefix=".third-party") and desired_path(URL)
SUB_PATH_STR = ".third-party/testowner/myrepo"
SUB_NAME = "testowner/myrepo"

REMOTE_ADDONS = ["my_addon", "other_addon"]


def _make_config(force_scheme=None, current_path=".third-party"):
    cfg = MagicMock()
    cfg.submodules.force_scheme = force_scheme
    cfg.submodules.current_path = current_path
    return cfg


def _make_repo():
    repo = MagicMock()
    repo.index.diff.return_value = [MagicMock()]
    repo.index.commit.return_value = MagicMock(hexsha="ab" * 8)
    return repo


def _base_patches(tmp_path, mock_repo=None):
    """Return a dict of patches that make the happy path work."""
    if mock_repo is None:
        mock_repo = _make_repo()
    return {
        "oops.commands.submodules.add.config": _make_config(),
        "oops.commands.submodules.add.require_repository": MagicMock(return_value=(mock_repo, tmp_path)),
        "oops.commands.submodules.add.read_gitmodules": MagicMock(return_value=MagicMock()),
        "oops.commands.submodules.add.list_remote_addons": MagicMock(return_value=REMOTE_ADDONS),
        "oops.commands.submodules.add.commit_v2": MagicMock(
            return_value=MagicMock(messages=[], warnings=[], errors=[])
        ),
        "oops.commands.submodules.add.create_symlink": MagicMock(return_value=None),
    }


class _apply_patches:
    """Context manager that applies a dict of {target: mock_or_value} patches."""

    def __init__(self, patches):
        self._patches = patches
        self._patcher_stack = []

    def __enter__(self):
        for target, mock in self._patches.items():
            p = patch(target, mock)
            p.start()
            self._patcher_stack.append(p)
        return self

    def __exit__(self, *_):
        for p in reversed(self._patcher_stack):
            p.stop()


def _invoke(tmp_path, args=None, extra_patches=None):
    """Invoke `oops submodules add` with standard mocks; return (result, patches)."""
    patches = _base_patches(tmp_path)
    if extra_patches:
        patches.update(extra_patches)
    with _apply_patches(patches):
        # --force skips interactive prompts; --addons bypasses prompt_choices
        result = CliRunner().invoke(main, args or [URL, BRANCH, "-f", "--token", "tok"])
    return result, patches


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
# Addon list fetching
# ---------------------------------------------------------------------------


class TestAddonFetch:
    def test_list_remote_addons_called_with_correct_args(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        patches["oops.commands.submodules.add.list_remote_addons"].assert_called_once_with(
            "testowner", "myrepo", BRANCH, "tok"
        )

    def test_no_addons_found_proceeds_without_symlinks(self, tmp_path):
        result, patches = _invoke(
            tmp_path,
            extra_patches={"oops.commands.submodules.add.list_remote_addons": MagicMock(return_value=[])},
        )
        assert result.exit_code == 0, result.output
        patches["oops.commands.submodules.add.create_symlink"].assert_not_called()


# ---------------------------------------------------------------------------
# --addons option
# ---------------------------------------------------------------------------


class TestAddonsOption:
    def test_addons_option_filters_to_requested(self, tmp_path):
        result, patches = _invoke(tmp_path, args=[URL, BRANCH, "-f", "--addons", "my_addon", "--token", "tok"])
        assert result.exit_code == 0, result.output
        create = patches["oops.commands.submodules.add.create_symlink"]
        called_names = [c.args[0].name for c in create.call_args_list]
        assert "my_addon" in called_names
        assert "other_addon" not in called_names

    def test_unknown_addon_exits_error(self, tmp_path):
        result, _ = _invoke(tmp_path, args=[URL, BRANCH, "-f", "--addons", "nonexistent", "--token", "tok"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# --force selects all addons
# ---------------------------------------------------------------------------


class TestForce:
    def test_force_symlinks_all_addons(self, tmp_path):
        result, patches = _invoke(tmp_path)  # _invoke uses -f by default
        assert result.exit_code == 0, result.output
        create = patches["oops.commands.submodules.add.create_symlink"]
        assert create.call_count == len(REMOTE_ADDONS)


# ---------------------------------------------------------------------------
# --no-commit
# ---------------------------------------------------------------------------


class TestNoCommit:
    def test_no_commit_skips_commit_v2(self, tmp_path):
        result, patches = _invoke(tmp_path, args=[URL, BRANCH, "-f", "--no-commit", "--token", "tok"])
        assert result.exit_code == 0, result.output
        patches["oops.commands.submodules.add.commit_v2"].assert_not_called()

    def test_no_commit_prints_warning(self, tmp_path):
        result, _ = _invoke(tmp_path, args=[URL, BRANCH, "-f", "--no-commit", "--token", "tok"])
        assert result.exit_code == 0, result.output
        assert "commit" in result.output.lower()


# ---------------------------------------------------------------------------
# Commit args
# ---------------------------------------------------------------------------


class TestCommit:
    def test_commit_v2_called_with_submodule_add_message(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        commit_mock = patches["oops.commands.submodules.add.commit_v2"]
        commit_mock.assert_called_once()
        message_name = commit_mock.call_args[0][3]
        assert message_name == "submodule_add"

    def test_commit_v2_called_with_already_staged(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        commit_mock = patches["oops.commands.submodules.add.commit_v2"]
        kwargs = commit_mock.call_args[1]
        assert kwargs.get("already_staged") is True
