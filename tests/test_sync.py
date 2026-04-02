"""Tests for oops.commands.project.sync."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import git as gitlib
from click.testing import CliRunner

from oops.commands.project.sync import _apply, _show_diff, main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(remote_url="https://example.com/repo.git", files=None):
    cfg = MagicMock()
    cfg.sync.remote_url = remote_url
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
# main — dry-run
# ---------------------------------------------------------------------------


class TestMainDryRun:
    def test_dry_run_no_changes(self):
        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config()), \
             patch("oops.commands.project.sync._fetch"), \
             patch("oops.commands.project.sync._show_diff", return_value=False):
            result = runner.invoke(main, ["--dry-run"])
        assert result.exit_code == 0
        assert "Already up to date" in result.output

    def test_dry_run_with_changes(self):
        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config()), \
             patch("oops.commands.project.sync._fetch"), \
             patch("oops.commands.project.sync._show_diff", return_value=True):
            result = runner.invoke(main, ["--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.output
        assert "No changes applied" in result.output


# ---------------------------------------------------------------------------
# main — apply + commit
# ---------------------------------------------------------------------------


class TestMainApply:
    def test_yes_flag_applies_and_commits(self, tmp_path):
        mock_repo = _make_local_repo(tmp_path)
        mock_repo.index.diff.return_value = [MagicMock()]  # non-empty = staged changes exist
        mock_commit = MagicMock()
        mock_commit.hexsha = "abcd1234efgh5678"
        mock_repo.index.commit.return_value = mock_commit

        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config(files=["Makefile"])), \
             patch("oops.commands.project.sync._fetch"), \
             patch("oops.commands.project.sync._show_diff", return_value=True), \
             patch("oops.commands.project.sync._apply"), \
             patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            result = runner.invoke(main, ["--yes"])

        assert result.exit_code == 0
        mock_repo.index.add.assert_called_once_with([str(tmp_path / "Makefile")])
        mock_repo.index.commit.assert_called_once()

    def test_nothing_to_commit(self, tmp_path):
        mock_repo = _make_local_repo(tmp_path)
        mock_repo.index.diff.return_value = []  # empty = nothing staged

        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config(files=["Makefile"])), \
             patch("oops.commands.project.sync._fetch"), \
             patch("oops.commands.project.sync._show_diff", return_value=True), \
             patch("oops.commands.project.sync._apply"), \
             patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            result = runner.invoke(main, ["--yes"])

        assert result.exit_code == 0
        assert "Nothing to commit" in result.output
        mock_repo.index.commit.assert_not_called()

    def test_index_add_uses_absolute_paths(self, tmp_path):
        """Regression: index.add must receive absolute paths so it works from any cwd."""
        mock_repo = _make_local_repo(tmp_path)
        mock_repo.index.diff.return_value = [MagicMock()]
        mock_repo.index.commit.return_value = MagicMock(hexsha="aa" * 8)

        runner = CliRunner()
        with patch("oops.commands.project.sync.config", _make_config(files=["a/b.txt"])), \
             patch("oops.commands.project.sync._fetch"), \
             patch("oops.commands.project.sync._show_diff", return_value=True), \
             patch("oops.commands.project.sync._apply"), \
             patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            runner.invoke(main, ["--yes"])

        added = mock_repo.index.add.call_args[0][0]
        assert all(path.startswith("/") for path in added), "Paths must be absolute"


# ---------------------------------------------------------------------------
# _show_diff
# ---------------------------------------------------------------------------


class TestShowDiff:
    def test_skips_file_missing_from_remote(self, tmp_path):
        local_root = tmp_path / "local"
        local_root.mkdir()
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()

        mock_repo = _make_local_repo(local_root)
        with patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            result = _show_diff(remote_dir, ["missing.txt"])

        assert result is False

    def test_new_file_detected(self, tmp_path):
        local_root = tmp_path / "local"
        local_root.mkdir()
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        (remote_dir / "newfile.txt").write_text("hello")

        mock_repo = _make_local_repo(local_root)
        with patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            result = _show_diff(remote_dir, ["newfile.txt"])

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
        mock_repo.git.diff.return_value = ""  # exit code 0, no diff output

        with patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            result = _show_diff(remote_dir, ["file.txt"])

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

        with patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            result = _show_diff(remote_dir, ["file.txt"])

        assert result is True


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_copies_file(self, tmp_path):
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        local_root = tmp_path / "local"
        local_root.mkdir()
        (remote_dir / "Makefile").write_text("all:\n\techo hi\n")

        mock_repo = _make_local_repo(local_root)
        with patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            _apply(remote_dir, ["Makefile"])

        assert (local_root / "Makefile").read_text() == "all:\n\techo hi\n"

    def test_copies_directory(self, tmp_path):
        remote_dir = tmp_path / "remote"
        (remote_dir / "subdir").mkdir(parents=True)
        (remote_dir / "subdir" / "file.txt").write_text("content")
        local_root = tmp_path / "local"
        local_root.mkdir()

        mock_repo = _make_local_repo(local_root)
        with patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            _apply(remote_dir, ["subdir"])

        assert (local_root / "subdir" / "file.txt").read_text() == "content"

    def test_skips_missing_remote_file(self, tmp_path):
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        local_root = tmp_path / "local"
        local_root.mkdir()

        mock_repo = _make_local_repo(local_root)
        with patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            _apply(remote_dir, ["nonexistent.txt"])  # must not raise

        assert not (local_root / "nonexistent.txt").exists()

    def test_creates_parent_directories(self, tmp_path):
        remote_dir = tmp_path / "remote"
        (remote_dir / "deep" / "nested").mkdir(parents=True)
        (remote_dir / "deep" / "nested" / "file.txt").write_text("hi")
        local_root = tmp_path / "local"
        local_root.mkdir()

        mock_repo = _make_local_repo(local_root)
        with patch("oops.commands.project.sync.git.Repo", return_value=mock_repo):
            _apply(remote_dir, ["deep/nested/file.txt"])

        assert (local_root / "deep" / "nested" / "file.txt").read_text() == "hi"
