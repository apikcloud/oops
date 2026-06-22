"""Tests for oops.commands.project.sync."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import git as gitlib
import pytest
from click.testing import CliRunner
from oops.commands.project.sync import main
from oops.core.models import Result
from oops.services.git import commit, show_diff
from oops.utils.net import sparse_clone

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(remote_url="https://example.com/repo.git", files=None, branch=None):
    cfg = MagicMock()
    cfg.sync.remote_url = remote_url
    cfg.sync.branch = branch
    cfg.sync.files = files if files is not None else ["Makefile"]
    return cfg


def _make_local_repo(tmp_path):
    mock_repo = MagicMock()
    mock_repo.working_tree_dir = str(tmp_path)
    return mock_repo


# ---------------------------------------------------------------------------
# main — guard checks
# ---------------------------------------------------------------------------


class TestMainGuards:
    def test_missing_remote_url_raises(self):
        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config(remote_url=None)):
            result = runner.invoke(main, [])
        assert result.exit_code != 0
        assert "sync.remote_url" in result.output

    def test_empty_remote_url_raises(self):
        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config(remote_url="")):
            result = runner.invoke(main, [])
        assert result.exit_code != 0
        assert "sync.remote_url" in result.output

    def test_empty_files_raises(self):
        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config(files=[])):
            result = runner.invoke(main, [])
        assert result.exit_code != 0
        assert "sync.files" in result.output


# ---------------------------------------------------------------------------
# main — no changes / early exit
# ---------------------------------------------------------------------------


class TestMainNoChanges:
    def test_no_changes_exits_clean(self, tmp_path):
        mock_repo = _make_local_repo(tmp_path)
        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config()), patch(
            "oops.commands.project.sync.require_repository", return_value=(mock_repo, tmp_path)
        ), patch("oops.commands.project.sync.fetch_project_files"), patch(
            "oops.commands.project.sync.show_diff", return_value=False
        ):
            result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "Already up to date" in result.output


# ---------------------------------------------------------------------------
# main — apply + commit
# ---------------------------------------------------------------------------


class TestMainApply:
    def _invoke(self, tmp_path, cfg, synced_files=("Makefile",), extra_args=()):
        """Run sync with all external I/O mocked.

        fetch_project_files side_effect creates synced_files in the real tmpdir
        so that _build_plan sees the correct existing-files set.
        run_mutation_workflow and render_and_raise are mocked to avoid terminal
        rendering in tests.
        """

        def fake_fetch(_url, _branch, _files, tmpdir):
            for f in synced_files:
                (tmpdir / f).write_text("")

        mock_commit = MagicMock(return_value=Result())
        runner = CliRunner()
        with patch("oops.commands.project.sync.config", cfg), patch(
            "oops.commands.project.sync.require_repository",
            return_value=(_make_local_repo(tmp_path), tmp_path),
        ), patch(
            "oops.commands.project.sync.fetch_project_files", side_effect=fake_fetch
        ), patch(
            "oops.commands.project.sync.show_diff", return_value=True
        ), patch(
            "oops.commands.project.sync.run_mutation_workflow", return_value=Result()
        ), patch(
            "oops.commands.project.sync.render_and_raise"
        ), patch(
            "oops.commands.project.sync.commit_v2", mock_commit
        ):
            result = runner.invoke(main, ["--force", *extra_args])
        return result, mock_commit

    def test_force_applies_and_commits(self, tmp_path):
        result, mock_commit = self._invoke(tmp_path, _make_config(files=["Makefile"]))
        assert result.exit_code == 0
        mock_commit.assert_called_once()
        assert mock_commit.call_args[0][2] == ["Makefile"]
        assert mock_commit.call_args[0][3] == "project_sync"

    def test_empty_applied_skips_commit(self, tmp_path):
        # No files in remote → _build_plan has no actionable items → commit skipped.
        result, mock_commit = self._invoke(
            tmp_path, _make_config(files=["Makefile"]), synced_files=()
        )
        assert result.exit_code == 0
        mock_commit.assert_not_called()

    def test_no_commit_skips_commit_v2(self, tmp_path):
        result, mock_commit = self._invoke(
            tmp_path, _make_config(files=["Makefile"]), extra_args=["--no-commit"]
        )
        assert result.exit_code == 0
        mock_commit.assert_not_called()

    def test_branch_forwarded_to_fetch_project_files(self, tmp_path):
        mock_repo = _make_local_repo(tmp_path)
        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config(branch="main")), patch(
            "oops.commands.project.sync.require_repository", return_value=(mock_repo, tmp_path)
        ), patch(
            "oops.commands.project.sync.fetch_project_files"
        ) as mock_fetch, patch(
            "oops.commands.project.sync.show_diff", return_value=False
        ):
            runner.invoke(main, [])

        _, branch_arg, _, _ = mock_fetch.call_args[0]
        assert branch_arg == "main"


# ---------------------------------------------------------------------------
# sparse_clone
# ---------------------------------------------------------------------------


class TestSparseClone:
    def _make_mock_repo(self, tmpdir):
        """Return a mock Repo whose config_writer context manager writes to a real path."""
        mock_repo = MagicMock()
        git_info = tmpdir / ".git" / "info"
        git_info.mkdir(parents=True)
        return mock_repo

    def test_clone_without_branch(self, tmp_path):
        mock_repo = self._make_mock_repo(tmp_path)
        with patch("oops.utils.net.Repo") as mock_repo_cls:
            mock_repo_cls.clone_from.return_value = mock_repo
            sparse_clone("https://example.com/repo.git", tmp_path, ["Makefile"])

        call_kwargs = mock_repo_cls.clone_from.call_args[1]
        assert "branch" not in call_kwargs

    def test_clone_with_branch(self, tmp_path):
        mock_repo = self._make_mock_repo(tmp_path)
        with patch("oops.utils.net.Repo") as mock_repo_cls:
            mock_repo_cls.clone_from.return_value = mock_repo
            sparse_clone("https://example.com/repo.git", tmp_path, ["Makefile"], "develop")

        call_kwargs = mock_repo_cls.clone_from.call_args[1]
        assert call_kwargs["branch"] == "develop"


# ---------------------------------------------------------------------------
# show_diff
# ---------------------------------------------------------------------------


class TestShowDiff:
    def test_skips_file_missing_from_remote(self, tmp_path):
        local_root = tmp_path / "local"
        local_root.mkdir()
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()

        mock_repo = _make_local_repo(local_root)
        result = show_diff(remote_dir, ["missing.txt"], mock_repo, local_root)
        assert result is False

    def test_new_file_detected(self, tmp_path):
        local_root = tmp_path / "local"
        local_root.mkdir()
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        (remote_dir / "newfile.txt").write_text("hello")

        mock_repo = _make_local_repo(local_root)
        result = show_diff(remote_dir, ["newfile.txt"], mock_repo, local_root)
        assert result is True

    def test_identical_files_no_changes(self, tmp_path):
        local_root = tmp_path / "local"
        local_root.mkdir()
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        content = "same content\n"
        (remote_dir / "file.txt").write_text(content)
        (local_root / "file.txt").write_text(content)

        mock_repo = _make_local_repo(local_root)
        mock_repo.git.diff.return_value = ""

        result = show_diff(remote_dir, ["file.txt"], mock_repo, local_root)
        assert result is False

    def test_changed_file_detected(self, tmp_path):
        local_root = tmp_path / "local"
        local_root.mkdir()
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        (remote_dir / "file.txt").write_text("new content\n")
        (local_root / "file.txt").write_text("old content\n")

        mock_repo = _make_local_repo(local_root)
        exc = gitlib.GitCommandError("diff", 1)
        exc.stdout = "--- a/file.txt\n+++ b/file.txt\n-old\n+new\n"
        mock_repo.git.diff.side_effect = exc

        result = show_diff(remote_dir, ["file.txt"], mock_repo, local_root)
        assert result is True


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------


class TestCommit:
    def test_commits_staged_files(self, tmp_path):
        mock_repo = _make_local_repo(tmp_path)
        mock_repo.index.diff.return_value = [MagicMock()]
        mock_commit = MagicMock()
        mock_commit.hexsha = "abcd1234efgh5678"
        mock_repo.index.commit.return_value = mock_commit

        commit(mock_repo, tmp_path, ["Makefile"], "project_sync")

        mock_repo.index.add.assert_called_once_with([str(tmp_path / "Makefile")])
        mock_repo.index.commit.assert_called_once()

    def test_add_uses_absolute_paths(self, tmp_path):
        """Regression: index.add must receive absolute paths regardless of cwd."""
        mock_repo = _make_local_repo(tmp_path)
        mock_repo.index.diff.return_value = [MagicMock()]
        mock_repo.index.commit.return_value = MagicMock(hexsha="aa" * 8)

        commit(mock_repo, tmp_path, ["a/b.txt"], "project_sync")

        added = mock_repo.index.add.call_args[0][0]
        assert all(Path(p).is_absolute() for p in added)

    def test_nothing_to_commit(self, tmp_path):
        mock_repo = _make_local_repo(tmp_path)
        mock_repo.index.diff.return_value = []

        commit(mock_repo, tmp_path, ["Makefile"], "project_sync")

        mock_repo.index.commit.assert_not_called()

    def test_unknown_message_name_raises(self, tmp_path):
        mock_repo = _make_local_repo(tmp_path)
        mock_repo.index.diff.return_value = [MagicMock()]

        with pytest.raises(ValueError, match="Unknown commit message name"):
            commit(mock_repo, tmp_path, ["Makefile"], "nonexistent_key")
