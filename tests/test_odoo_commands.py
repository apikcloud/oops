# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: test_odoo_commands.py — tests/test_odoo_commands.py

"""Tests for oops/utils/git.py and the three odoo CLI commands."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import click
import pytest
from click.testing import CliRunner

from oops.commands.odoo.download import main as download_main
from oops.commands.odoo.show import main as show_main
from oops.commands.odoo.update import main as update_main
from oops.core.config import OdooConfig, _apply
from oops.utils.git import (
    _git,
    _git_output,
    clone,
    repo_info,
    update_at_date,
    update_latest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A minimal config mock that makes OopsCommand.invoke() happy (no file needed).
def _make_config_mock(sources_dir=None):
    cfg = MagicMock()
    cfg.default_timeout = 60
    cfg.odoo = MagicMock()
    cfg.odoo.sources_dir = sources_dir
    cfg.odoo.community_url = "git@github.com:odoo/odoo.git"
    cfg.odoo.enterprise_url = "git@github.com:odoo/enterprise.git"
    return cfg


# ---------------------------------------------------------------------------
# oops/utils/git.py
# ---------------------------------------------------------------------------


class TestGit:
    def test_git_calls_subprocess_with_check(self):
        with patch("oops.utils.git.subprocess.run") as mock_run:
            _git("status")
            mock_run.assert_called_once_with(["git", "status"], check=True, cwd=None)

    def test_git_passes_cwd(self, tmp_path):
        with patch("oops.utils.git.subprocess.run") as mock_run:
            _git("status", cwd=tmp_path)
            mock_run.assert_called_once_with(["git", "status"], check=True, cwd=tmp_path)

    def test_git_passes_multiple_args(self):
        with patch("oops.utils.git.subprocess.run") as mock_run:
            _git("fetch", "--depth", "1")
            mock_run.assert_called_once_with(
                ["git", "fetch", "--depth", "1"], check=True, cwd=None
            )

    def test_git_output_returns_stripped_stdout(self):
        mock_result = MagicMock()
        mock_result.stdout = "  abc123  \n"
        with patch("oops.utils.git.subprocess.run", return_value=mock_result) as mock_run:
            result = _git_output("log", "-1")
            assert result == "abc123"
            mock_run.assert_called_once_with(
                ["git", "log", "-1"],
                check=True,
                cwd=None,
                capture_output=True,
                text=True,
            )

    def test_git_output_passes_cwd(self, tmp_path):
        mock_result = MagicMock()
        mock_result.stdout = "hash\n"
        with patch("oops.utils.git.subprocess.run", return_value=mock_result) as mock_run:
            _git_output("rev-parse", "HEAD", cwd=tmp_path)
            mock_run.assert_called_once_with(
                ["git", "rev-parse", "HEAD"],
                check=True,
                cwd=tmp_path,
                capture_output=True,
                text=True,
            )


class TestClone:
    def test_clone_calls_git_with_correct_args(self, tmp_path):
        dest = tmp_path / "odoo"
        with patch("oops.utils.git._git") as mock_git:
            clone("git@github.com:odoo/odoo.git", dest, "17.0")
            mock_git.assert_called_once_with(
                "clone",
                "git@github.com:odoo/odoo.git",
                "--branch",
                "17.0",
                "--depth",
                "1",
                "--single-branch",
                str(dest),
            )


class TestUpdateLatest:
    def test_update_latest_calls_fetch_then_reset(self, tmp_path):
        with patch("oops.utils.git._git") as mock_git:
            update_latest(tmp_path)
            assert mock_git.call_count == 2
            mock_git.assert_any_call("fetch", "--depth", "1", cwd=tmp_path)
            mock_git.assert_any_call("reset", "--hard", "FETCH_HEAD", cwd=tmp_path)

    def test_update_latest_order(self, tmp_path):
        calls = []
        with patch("oops.utils.git._git", side_effect=lambda *a, **kw: calls.append(a)):
            update_latest(tmp_path)
        assert calls[0] == ("fetch", "--depth", "1")
        assert calls[1] == ("reset", "--hard", "FETCH_HEAD")


class TestRepoInfo:
    def test_nonexistent_dir_returns_empty(self, tmp_path):
        missing = tmp_path / "nonexistent"
        assert repo_info(missing) == ""

    def test_existing_dir_returns_git_output(self, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        with patch(
            "oops.utils.git._git_output", return_value="abc1234  2024-01-15 10:00:00 +0200"
        ):
            result = repo_info(tmp_path)
        assert result == "abc1234  2024-01-15 10:00:00 +0200"

    def test_called_process_error_returns_empty(self, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        with patch(
            "oops.utils.git._git_output",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            result = repo_info(tmp_path)
        assert result == ""

    def test_empty_git_output_returns_empty(self, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        with patch("oops.utils.git._git_output", return_value=""):
            result = repo_info(tmp_path)
        assert result == ""


class TestUpdateAtDate:
    def test_normal_flow_checks_out_commit(self, tmp_path):
        commit_hash = "deadbeef1234"
        with patch("oops.utils.git._git") as mock_git, patch(
            "oops.utils.git._git_output", return_value=commit_hash
        ):
            update_at_date(tmp_path, "2024-01-15")
            mock_git.assert_any_call("fetch", "--shallow-since", "2024-01-15", cwd=tmp_path)
            mock_git.assert_any_call("checkout", commit_hash, cwd=tmp_path)

    def test_no_commit_raises_click_exception(self, tmp_path):
        with patch("oops.utils.git._git"), patch(
            "oops.utils.git._git_output", return_value=""
        ):
            with pytest.raises(click.ClickException, match="No commit found at or before"):
                update_at_date(tmp_path, "2020-01-01")

    def test_rev_list_args(self, tmp_path):
        commit_hash = "cafebabe"
        captured_calls = []

        def fake_git_output(*args, **kwargs):
            captured_calls.append((args, kwargs))
            return commit_hash

        with patch("oops.utils.git._git"), patch(
            "oops.utils.git._git_output", side_effect=fake_git_output
        ):
            update_at_date(tmp_path, "2024-06-30")

        assert len(captured_calls) == 1
        args, kwargs = captured_calls[0]
        assert args == ("rev-list", "-1", "--before=2024-06-30 23:59:59", "FETCH_HEAD")
        assert kwargs.get("cwd") == tmp_path


# ---------------------------------------------------------------------------
# oops/commands/odoo/download.py
# ---------------------------------------------------------------------------


class TestDownloadCommand:
    def _runner(self):
        return CliRunner()

    def test_version_normalization_short_form(self, tmp_path):
        """'19' should be treated as '19.0'."""
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            result = self._runner().invoke(download_main, ["19", "--no-enterprise"])
        # community_dir is resolved as <tmp_path>/19.0/community
        expected_community = tmp_path / "19.0" / "community"
        mock_clone.assert_called_once_with(
            cfg_mock.odoo.community_url, expected_community, "19.0"
        )
        assert result.exit_code == 0

    def test_version_with_dot_unchanged(self, tmp_path):
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            self._runner().invoke(download_main, ["17.0", "--no-enterprise"])
        expected_community = tmp_path / "17.0" / "community"
        mock_clone.assert_called_once_with(
            cfg_mock.odoo.community_url, expected_community, "17.0"
        )

    def test_missing_sources_dir_raises_usage_error(self):
        """No --base-dir and config.odoo.sources_dir is None → UsageError."""
        cfg_mock = _make_config_mock(sources_dir=None)
        with patch("oops.commands.odoo.download.config", cfg_mock):
            result = self._runner().invoke(download_main, ["17.0"])
        assert result.exit_code != 0
        assert "No base directory provided" in result.output

    def test_clone_community_when_dir_does_not_exist(self, tmp_path):
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            result = self._runner().invoke(download_main, ["17.0", "--no-enterprise"])
        mock_clone.assert_called_once()
        assert result.exit_code == 0

    def test_skip_community_with_warning_when_dir_exists(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            result = self._runner().invoke(download_main, ["17.0", "--no-enterprise"])
        mock_clone.assert_not_called()
        assert "already exists" in result.output
        assert result.exit_code == 0

    def test_update_community_when_dir_exists_and_update_flag(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.update_latest"
        ) as mock_update:
            result = self._runner().invoke(download_main, ["17.0", "--update", "--no-enterprise"])
        mock_update.assert_called_once_with(community_dir)
        assert result.exit_code == 0

    def test_enterprise_cloned_by_default(self, tmp_path):
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        clone_calls = []
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone", side_effect=lambda *a: clone_calls.append(a)
        ):
            result = self._runner().invoke(download_main, ["17.0"])
        assert len(clone_calls) == 2
        cloned_dests = [c[1] for c in clone_calls]
        assert any("community" in str(d) for d in cloned_dests)
        assert any("enterprise" in str(d) for d in cloned_dests)
        assert result.exit_code == 0

    def test_no_enterprise_flag_clones_community_only(self, tmp_path):
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        clone_calls = []
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone", side_effect=lambda *a: clone_calls.append(a)
        ):
            self._runner().invoke(download_main, ["17.0", "--no-enterprise"])
        assert len(clone_calls) == 1
        assert clone_calls[0][1].name == "community"

    def test_clone_failure_exits_with_code_1(self, tmp_path):
        """Exit(1) is raised when errors accumulate (both repos attempted by default)."""
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            result = self._runner().invoke(download_main, ["17.0"])
        assert result.exit_code == 1

    def test_community_clone_failure_no_enterprise_no_exit_code_1(self, tmp_path):
        """Community-only clone failure does not raise Exit(1) — execution returns
        before the error-check block (which is after the enterprise section)."""
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            result = self._runner().invoke(download_main, ["17.0", "--no-enterprise"])
        assert result.exit_code == 0

    def test_base_dir_option_overrides_config(self, tmp_path):
        """--base-dir should be used even when config has a sources_dir."""
        cfg_mock = _make_config_mock(sources_dir=Path("/some/other/path"))
        custom_base = tmp_path / "custom"
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            self._runner().invoke(
                download_main, ["17.0", "--no-enterprise", "--base-dir", str(custom_base)]
            )
        expected_community = custom_base / "17.0" / "community"
        mock_clone.assert_called_once_with(
            cfg_mock.odoo.community_url, expected_community, "17.0"
        )

    def test_enterprise_clone_failure_accumulates_error(self, tmp_path):
        cfg_mock = _make_config_mock(sources_dir=tmp_path)

        def fake_clone(url, dest, branch):
            if "enterprise" in str(dest):
                raise subprocess.CalledProcessError(1, "git")

        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.clone", side_effect=fake_clone
        ):
            result = self._runner().invoke(download_main, ["17.0"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# oops/commands/odoo/update.py
# ---------------------------------------------------------------------------


class TestUpdateCommand:
    def _runner(self):
        return CliRunner()

    def test_version_normalization(self, tmp_path):
        community_dir = tmp_path / "19.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.update.config", cfg_mock), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["19"])
        mock_update.assert_called_once_with(community_dir)
        assert result.exit_code == 0

    def test_missing_sources_dir_raises_usage_error(self):
        cfg_mock = _make_config_mock(sources_dir=None)
        with patch("oops.commands.odoo.update.config", cfg_mock):
            result = self._runner().invoke(update_main, ["17.0"])
        assert result.exit_code != 0
        assert "No base directory provided" in result.output

    def test_update_latest_called_without_date(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.update.config", cfg_mock), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["17.0"])
        mock_update.assert_called_once_with(community_dir)
        assert result.exit_code == 0

    def test_update_at_date_called_with_date_flag(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.update.config", cfg_mock), patch(
            "oops.commands.odoo.update.update_at_date"
        ) as mock_uad:
            result = self._runner().invoke(update_main, ["17.0", "--date", "2024-01-15"])
        mock_uad.assert_called_once_with(community_dir, "2024-01-15")
        assert result.exit_code == 0

    def test_enterprise_updated_by_default(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        community_dir.mkdir(parents=True)
        enterprise_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.update.config", cfg_mock), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["17.0"])
        assert mock_update.call_count == 2
        updated_paths = {c.args[0] for c in mock_update.call_args_list}
        assert community_dir in updated_paths
        assert enterprise_dir in updated_paths
        assert result.exit_code == 0

    def test_no_enterprise_flag_updates_community_only(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.update.config", cfg_mock), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["17.0", "--no-enterprise"])
        assert mock_update.call_count == 1
        assert mock_update.call_args.args[0] == community_dir
        assert result.exit_code == 0

    def test_dest_not_found_prints_warning_and_continues(self, tmp_path):
        """If community dir does not exist, warn and continue (no crash, exit 0)."""
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.update.config", cfg_mock), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["17.0"])
        mock_update.assert_not_called()
        assert "not found" in result.output
        assert result.exit_code == 0

    def test_base_dir_option_used(self, tmp_path):
        custom_base = tmp_path / "sources"
        community_dir = custom_base / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=Path("/ignored"))
        with patch("oops.commands.odoo.update.config", cfg_mock), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            self._runner().invoke(
                update_main, ["17.0", "--base-dir", str(custom_base)]
            )
        mock_update.assert_called_once_with(community_dir)

    def test_update_failure_exits_with_code_1(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.update.config", cfg_mock), patch(
            "oops.commands.odoo.update.update_latest",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            result = self._runner().invoke(update_main, ["17.0"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# oops/commands/odoo/show.py
# ---------------------------------------------------------------------------


class TestShowCommand:
    def _runner(self):
        return CliRunner()

    def test_missing_sources_dir_raises_usage_error(self):
        cfg_mock = _make_config_mock(sources_dir=None)
        with patch("oops.commands.odoo.show.config", cfg_mock):
            result = self._runner().invoke(show_main, [])
        assert result.exit_code != 0
        assert "No base directory provided" in result.output

    def test_sources_dir_does_not_exist(self, tmp_path):
        missing = tmp_path / "nonexistent"
        cfg_mock = _make_config_mock(sources_dir=missing)
        with patch("oops.commands.odoo.show.config", cfg_mock):
            result = self._runner().invoke(show_main, [])
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_empty_sources_dir_reports_no_version_dirs(self, tmp_path):
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.show.config", cfg_mock):
            result = self._runner().invoke(show_main, [])
        assert result.exit_code == 0
        assert "No version directories found" in result.output

    def test_show_with_community_only(self, tmp_path):
        # Use a non-numeric version name so tabulate does not strip the decimal part
        version_dir = tmp_path / "odoo-17"
        community_dir = version_dir / "community"
        community_dir.mkdir(parents=True)

        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        fake_info = "abc1234  2024-01-15 10:00:00 +0200"

        def fake_repo_info(path):
            if path == community_dir:
                return fake_info
            return ""

        with patch("oops.commands.odoo.show.config", cfg_mock), patch(
            "oops.commands.odoo.show.repo_info", side_effect=fake_repo_info
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "odoo-17" in result.output
        assert fake_info in result.output

    def test_show_with_community_and_enterprise(self, tmp_path):
        version_dir = tmp_path / "odoo-17"
        community_dir = version_dir / "community"
        enterprise_dir = version_dir / "enterprise"
        community_dir.mkdir(parents=True)
        enterprise_dir.mkdir(parents=True)

        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        community_info = "abc1234  2024-01-15 10:00:00 +0200"
        enterprise_info = "def5678  2024-01-15 10:00:00 +0200"

        def fake_repo_info(path):
            if path == community_dir:
                return community_info
            if path == enterprise_dir:
                return enterprise_info
            return ""

        with patch("oops.commands.odoo.show.config", cfg_mock), patch(
            "oops.commands.odoo.show.repo_info", side_effect=fake_repo_info
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert community_info in result.output
        assert enterprise_info in result.output

    def test_version_dirs_with_no_repos_shows_no_checkouts(self, tmp_path):
        version_dir = tmp_path / "17.0"
        version_dir.mkdir()

        cfg_mock = _make_config_mock(sources_dir=tmp_path)

        with patch("oops.commands.odoo.show.config", cfg_mock), patch(
            "oops.commands.odoo.show.repo_info", return_value=""
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "No Odoo checkouts found" in result.output

    def test_base_dir_option_overrides_config(self, tmp_path):
        custom = tmp_path / "custom_sources"
        custom.mkdir()
        cfg_mock = _make_config_mock(sources_dir=Path("/ignored"))

        with patch("oops.commands.odoo.show.config", cfg_mock):
            result = self._runner().invoke(show_main, ["--base-dir", str(custom)])

        assert result.exit_code == 0
        assert "No version directories found" in result.output

    def test_multiple_version_dirs_shown(self, tmp_path):
        for version in ("odoo-17", "odoo-18"):
            community_dir = tmp_path / version / "community"
            community_dir.mkdir(parents=True)

        cfg_mock = _make_config_mock(sources_dir=tmp_path)

        def fake_repo_info(path):
            if path.name == "community":
                return "hash  2024-01-01 +0000"
            return ""

        with patch("oops.commands.odoo.show.config", cfg_mock), patch(
            "oops.commands.odoo.show.repo_info", side_effect=fake_repo_info
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "odoo-17" in result.output
        assert "odoo-18" in result.output


# ---------------------------------------------------------------------------
# OdooConfig in oops/core/config.py
# ---------------------------------------------------------------------------


class TestOdooConfig:
    def test_apply_converts_string_to_path(self):
        from oops.core.config import Config

        cfg = Config()
        _apply(cfg, {"odoo": {"sources_dir": "/tmp/odoo_sources"}})
        assert cfg.odoo.sources_dir == Path("/tmp/odoo_sources")
        assert isinstance(cfg.odoo.sources_dir, Path)

    def test_apply_expands_tilde(self):
        from oops.core.config import Config

        cfg = Config()
        _apply(cfg, {"odoo": {"sources_dir": "~/odoo"}})
        assert not str(cfg.odoo.sources_dir).startswith("~")
        assert cfg.odoo.sources_dir == Path("~/odoo").expanduser()

    def test_apply_none_stays_none(self):
        from oops.core.config import Config

        cfg = Config()
        assert cfg.odoo.sources_dir is None

    def test_apply_path_instance(self):
        from oops.core.config import Config

        cfg = Config()
        _apply(cfg, {"odoo": {"sources_dir": Path("/abs/path")}})
        assert cfg.odoo.sources_dir == Path("/abs/path")

    def test_apply_community_url(self):
        from oops.core.config import Config

        cfg = Config()
        _apply(cfg, {"odoo": {"community_url": "git@github.com:my-fork/odoo.git"}})
        assert cfg.odoo.community_url == "git@github.com:my-fork/odoo.git"

    def test_defaults(self):
        cfg = OdooConfig()
        assert cfg.sources_dir is None
        assert cfg.community_url == "git@github.com:odoo/odoo.git"
        assert cfg.enterprise_url == "git@github.com:odoo/enterprise.git"
