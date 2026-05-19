# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops.commands.submodules.clean."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.submodules.clean import (
    _HEAD_CHOICE,
    _recent_commits,
    _submodule_base_paths,
    _wipe_base_dirs,
    main,
)
from oops.core.exceptions import OopsError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_commit(sha="aabbccdd11223344", summary="Test commit", ts=1700000000):
    c = MagicMock()
    c.hexsha = sha
    c.summary = summary
    c.committed_date = ts
    return c


def _make_repo(commits=None):
    repo = MagicMock()
    repo.iter_commits.return_value = commits if commits is not None else [_make_commit()]
    repo.head.reset = MagicMock()
    repo.git.submodule = MagicMock()
    return repo


# ---------------------------------------------------------------------------
# _submodule_base_paths
# ---------------------------------------------------------------------------


class TestSubmoduleBasePaths:
    def test_iterates_full_old_paths(self, tmp_path, monkeypatch):
        cfg = MagicMock()
        cfg.submodules.old_paths = [Path("a"), Path("b")]
        cfg.submodules.current_path = Path("c")
        monkeypatch.setattr("oops.commands.submodules.clean.config", cfg)

        result = _submodule_base_paths(tmp_path)

        assert result == [tmp_path / "a", tmp_path / "b", tmp_path / "c"]

    def test_empty_old_paths_no_index_error(self, tmp_path, monkeypatch):
        cfg = MagicMock()
        cfg.submodules.old_paths = []
        cfg.submodules.current_path = Path("c")
        monkeypatch.setattr("oops.commands.submodules.clean.config", cfg)

        result = _submodule_base_paths(tmp_path)

        assert result == [tmp_path / "c"]


# ---------------------------------------------------------------------------
# _wipe_base_dirs
# ---------------------------------------------------------------------------


class TestWipeBaseDirs:
    def test_removes_existing_dirs(self, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        a.mkdir()
        b.mkdir()

        removed = _wipe_base_dirs([a, b])

        assert removed == [a, b]
        assert not a.exists()
        assert not b.exists()

    def test_skips_absent_dirs(self, tmp_path):
        assert _wipe_base_dirs([tmp_path / "ghost"]) == []

    def test_returns_only_removed(self, tmp_path):
        exists, absent = tmp_path / "exists", tmp_path / "absent"
        exists.mkdir()

        removed = _wipe_base_dirs([exists, absent])

        assert removed == [exists]


# ---------------------------------------------------------------------------
# _recent_commits
# ---------------------------------------------------------------------------


class TestRecentCommits:
    def test_first_entry_is_head_choice(self):
        choices, shas = _recent_commits(_make_repo([_make_commit()]), n=1)
        assert choices[0] == _HEAD_CHOICE
        assert shas[0] == "HEAD"

    def test_commit_entries_use_short_sha(self):
        commit = _make_commit(sha="aabb1122ccdd3344")
        choices, shas = _recent_commits(_make_repo([commit]), n=1)
        assert "aabb1122" in choices[1]
        assert shas[1] == "aabb1122ccdd3344"

    def test_respects_n(self):
        repo = _make_repo([])
        _recent_commits(repo, n=7)
        repo.iter_commits.assert_called_once_with("HEAD", max_count=7)


# ---------------------------------------------------------------------------
# main — guard
# ---------------------------------------------------------------------------


class TestMainGuards:
    def test_no_submodules_exits_1(self, tmp_path):
        runner = CliRunner()
        with patch(
            "oops.commands.submodules.clean.require_repository",
            return_value=(_make_repo(), tmp_path),
        ), patch(
            "oops.commands.submodules.clean.require_submodules",
            side_effect=OopsError("This command requires submodules."),
        ):
            result = runner.invoke(main, [])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# main — cancellation
# ---------------------------------------------------------------------------


class TestMainCancellation:
    """Each cancel path must exit 1 and never call _run_actions."""

    def _invoke(self, tmp_path, *, confirm_rv, select_rv: str | None = _HEAD_CHOICE):
        repo = _make_repo()
        runner = CliRunner()
        with patch(
            "oops.commands.submodules.clean.require_repository",
            return_value=(repo, tmp_path),
        ), patch(
            "oops.commands.submodules.clean.require_submodules",
        ), patch(
            "oops.commands.submodules.clean._print_step",
        ), patch(
            "oops.commands.submodules.clean.prompt_confirm",
            side_effect=confirm_rv if isinstance(confirm_rv, list) else [confirm_rv, confirm_rv],
        ), patch(
            "oops.commands.submodules.clean.prompt_select", return_value=select_rv
        ), patch(
            "oops.commands.submodules.clean._run_actions"
        ) as mock_run:
            result = runner.invoke(main, [])
        return result, mock_run

    def test_cancel_at_intro(self, tmp_path):
        result, mock_run = self._invoke(tmp_path, confirm_rv=[False])
        assert result.exit_code == 1
        mock_run.assert_not_called()

    def test_cancel_at_picker(self, tmp_path):
        result, mock_run = self._invoke(tmp_path, confirm_rv=[True], select_rv=None)
        assert result.exit_code == 1
        mock_run.assert_not_called()

    def test_cancel_at_final_confirm(self, tmp_path):
        result, mock_run = self._invoke(tmp_path, confirm_rv=[True, False])
        assert result.exit_code == 1
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# main — happy paths
# ---------------------------------------------------------------------------


class TestMainHappyPath:
    def _invoke(self, tmp_path, picker_answer, repo=None):
        if repo is None:
            repo = _make_repo()
        runner = CliRunner()
        with patch(
            "oops.commands.submodules.clean.require_repository",
            return_value=(repo, tmp_path),
        ), patch(
            "oops.commands.submodules.clean.require_submodules",
        ), patch(
            "oops.commands.submodules.clean._print_step",
        ), patch(
            "oops.commands.submodules.clean.prompt_confirm", return_value=True
        ), patch(
            "oops.commands.submodules.clean.prompt_select", return_value=picker_answer
        ), patch(
            "oops.commands.submodules.clean._run_actions"
        ) as mock_run, patch(
            "oops.commands.submodules.clean.conclude"
        ):
            result = runner.invoke(main, [])
        return result, mock_run

    def test_head_choice_passes_head_sha(self, tmp_path):
        result, mock_run = self._invoke(tmp_path, picker_answer=_HEAD_CHOICE)

        assert result.exit_code == 0, result.output
        _, target_sha, _ = mock_run.call_args.args
        assert target_sha == "HEAD"

    def test_commit_choice_passes_full_sha(self, tmp_path):
        commit = _make_commit(sha="deadbeefdeadbeef")
        repo = _make_repo([commit])
        choices, _ = _recent_commits(repo)
        display = choices[1]  # the commit entry built by _recent_commits

        result, mock_run = self._invoke(tmp_path, picker_answer=display, repo=_make_repo([commit]))

        assert result.exit_code == 0, result.output
        _, target_sha, _ = mock_run.call_args.args
        assert target_sha == "deadbeefdeadbeef"

    def test_base_paths_passed_to_run_actions(self, tmp_path, monkeypatch):
        cfg = MagicMock()
        cfg.submodules.old_paths = [Path("x")]
        cfg.submodules.current_path = Path("y")
        monkeypatch.setattr("oops.commands.submodules.clean.config", cfg)

        result, mock_run = self._invoke(tmp_path, picker_answer=_HEAD_CHOICE)

        assert result.exit_code == 0, result.output
        _, _, base_paths = mock_run.call_args.args
        assert base_paths == [tmp_path / "x", tmp_path / "y"]

    def test_reset_option_no_longer_accepted(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--reset"])
        assert result.exit_code == 2
        assert "No such option" in result.output
