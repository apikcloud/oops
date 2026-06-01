# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_odoo_commands.py — tests/test_odoo_commands.py

"""Tests for oops/utils/git.py and the three odoo CLI commands."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    cfg.odoo.themes_url = "git@github.com:odoo/design-themes.git"
    return cfg


# ---------------------------------------------------------------------------
# oops/utils/git.py
# ---------------------------------------------------------------------------


class TestGit:
    def test_git_calls_subprocess_with_check(self):
        with patch("oops.utils.git.subprocess.run") as mock_run:
            _git("status")
            mock_run.assert_called_once_with(["git", "status"], check=True, cwd=None, stdout=None, stderr=None)

    def test_git_passes_cwd(self, tmp_path):
        with patch("oops.utils.git.subprocess.run") as mock_run:
            _git("status", cwd=tmp_path)
            mock_run.assert_called_once_with(["git", "status"], check=True, cwd=tmp_path, stdout=None, stderr=None)

    def test_git_passes_multiple_args(self):
        with patch("oops.utils.git.subprocess.run") as mock_run:
            _git("fetch", "--depth", "1")
            mock_run.assert_called_once_with(
                ["git", "fetch", "--depth", "1"], check=True, cwd=None, stdout=None, stderr=None
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
                quiet=False,
            )


class TestUpdateLatest:
    def test_update_latest_calls_fetch_then_reset(self, tmp_path):
        with patch("oops.utils.git._git") as mock_git:
            update_latest(tmp_path)
            assert mock_git.call_count == 2
            mock_git.assert_any_call("fetch", "--depth", "1", cwd=tmp_path, quiet=False)
            mock_git.assert_any_call("reset", "--hard", "FETCH_HEAD", cwd=tmp_path, quiet=False)

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
        with patch("oops.utils.git._git_output", return_value="abc1234  2024-01-15 10:00:00 +0200"):
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
        with patch("oops.utils.git._git") as mock_git, patch("oops.utils.git._git_output", return_value=commit_hash):
            update_at_date(tmp_path, "2024-01-15")
            mock_git.assert_any_call("fetch", "--shallow-since", "2024-01-15", cwd=tmp_path, quiet=False)
            mock_git.assert_any_call("checkout", commit_hash, cwd=tmp_path, quiet=False)

    def test_no_commit_raises_click_exception(self, tmp_path):
        with patch("oops.utils.git._git"), patch("oops.utils.git._git_output", return_value=""):
            with pytest.raises(click.ClickException, match="No commit found at or before"):
                update_at_date(tmp_path, "2020-01-01")

    def test_rev_list_args(self, tmp_path):
        commit_hash = "cafebabe"
        captured_calls = []

        def fake_git_output(*args, **kwargs):
            captured_calls.append((args, kwargs))
            return commit_hash

        with patch("oops.utils.git._git"), patch("oops.utils.git._git_output", side_effect=fake_git_output):
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

    def _patch_dirs(self, community_dir, enterprise_dir=None, themes_dir=None):
        if enterprise_dir is None:
            enterprise_dir = community_dir.parent / "enterprise"
        if themes_dir is None:
            themes_dir = community_dir.parent / "themes"
        from oops.io.file import OdooSourcesDirs
        return patch(
            "oops.commands.odoo.download.get_odoo_sources_dirs",
            return_value=OdooSourcesDirs(
                community=community_dir,
                enterprise=enterprise_dir,
                themes=themes_dir,
            ),
        )

    def test_version_normalization_short_form(self, tmp_path):
        """'19' should be treated as '19.0'."""
        community_dir = tmp_path / "19.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            result = self._runner().invoke(download_main, ["--version", "19", "--no-enterprise", "--no-themes"])
        mock_clone.assert_called_once_with(cfg_mock.odoo.community_url, community_dir, "19.0", quiet=True)
        assert result.exit_code == 0

    def test_version_with_dot_unchanged(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            self._runner().invoke(download_main, ["--version", "17.0", "--no-enterprise", "--no-themes"])
        mock_clone.assert_called_once_with(cfg_mock.odoo.community_url, community_dir, "17.0", quiet=True)

    def test_missing_sources_dir_raises_usage_error(self):
        import click as _click
        with patch(
            "oops.commands.odoo.download.get_odoo_sources_dirs",
            side_effect=_click.UsageError("No base directory provided."),
        ):
            result = self._runner().invoke(download_main, ["--version", "17.0"])
        assert result.exit_code != 0
        assert "No base directory provided" in result.output

    def test_clone_community_when_dir_does_not_exist(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            result = self._runner().invoke(download_main, ["--version", "17.0", "--no-enterprise", "--no-themes"])
        mock_clone.assert_called_once()
        assert result.exit_code == 0

    def test_skip_community_with_warning_when_dir_exists(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.download.clone"
        ) as mock_clone:
            result = self._runner().invoke(download_main, ["--version", "17.0", "--no-enterprise", "--no-themes"])
        mock_clone.assert_not_called()
        assert "already exists" in result.output
        assert result.exit_code == 0

    def test_update_community_when_dir_exists_and_update_flag(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.download.update_latest"
        ) as mock_update:
            result = self._runner().invoke(
                download_main, ["--version", "17.0", "--update", "--no-enterprise", "--no-themes"]
            )
        mock_update.assert_called_once_with(community_dir, quiet=True)
        assert result.exit_code == 0

    def test_enterprise_cloned_by_default(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        themes_dir = tmp_path / "17.0" / "themes"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        clone_calls = []
        with patch("oops.commands.odoo.download.config", cfg_mock), \
                self._patch_dirs(community_dir, enterprise_dir, themes_dir), \
                patch("oops.commands.odoo.download.clone", side_effect=lambda *a, **kw: clone_calls.append(a)):
            result = self._runner().invoke(download_main, ["--version", "17.0"])
        assert len(clone_calls) == 3
        cloned_dests = [c[1] for c in clone_calls]
        assert any("community" in str(d) for d in cloned_dests)
        assert any("enterprise" in str(d) for d in cloned_dests)
        assert any("themes" in str(d) for d in cloned_dests)
        assert result.exit_code == 0

    def test_no_enterprise_flag_clones_community_only(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        clone_calls = []
        with patch("oops.commands.odoo.download.config", cfg_mock), self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.download.clone", side_effect=lambda *a, **kw: clone_calls.append(a)
        ):
            self._runner().invoke(download_main, ["--version", "17.0", "--no-enterprise", "--no-themes"])
        assert len(clone_calls) == 1
        assert clone_calls[0][1].name == "community"

    def test_clone_failure_exits_with_code_1(self, tmp_path):
        """Exit(1) is raised when errors accumulate (all three repos attempted by default)."""
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        themes_dir = tmp_path / "17.0" / "themes"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), \
                self._patch_dirs(community_dir, enterprise_dir, themes_dir), \
                patch("oops.commands.odoo.download.clone", side_effect=subprocess.CalledProcessError(1, "git")):
            result = self._runner().invoke(download_main, ["--version", "17.0"])
        assert result.exit_code == 1

    def test_community_only_failure_exits_with_code_1(self, tmp_path):
        """Community clone failure with --no-enterprise --no-themes now exits 1 (wart fixed)."""
        community_dir = tmp_path / "17.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.download.clone",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            result = self._runner().invoke(download_main, ["--version", "17.0", "--no-enterprise", "--no-themes"])
        assert result.exit_code == 1

    def test_get_odoo_sources_dirs_called_with_version(self, tmp_path):
        """get_odoo_sources_dirs receives the normalised version string."""
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        from oops.io.file import OdooSourcesDirs
        themes_dir = community_dir.parent / "themes"
        with patch("oops.commands.odoo.download.config", cfg_mock), patch(
            "oops.commands.odoo.download.get_odoo_sources_dirs",
            return_value=OdooSourcesDirs(community=community_dir, enterprise=enterprise_dir, themes=themes_dir),
        ) as mock_dirs, patch("oops.commands.odoo.download.clone"):
            self._runner().invoke(download_main, ["--version", "17.0", "--no-enterprise"])
        mock_dirs.assert_called_once_with("17.0")

    def test_enterprise_clone_failure_accumulates_error(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)

        def fake_clone(url, dest, branch, **kwargs):
            if "enterprise" in str(dest):
                raise subprocess.CalledProcessError(1, "git")

        with patch("oops.commands.odoo.download.config", cfg_mock), \
                self._patch_dirs(community_dir, enterprise_dir), \
                patch("oops.commands.odoo.download.clone", side_effect=fake_clone):
            result = self._runner().invoke(download_main, ["--version", "17.0", "--no-themes"])
        assert result.exit_code == 1

    def test_themes_cloned_by_default(self, tmp_path):
        """With no flags, themes is cloned alongside community and enterprise."""
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        themes_dir = tmp_path / "17.0" / "themes"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        clone_calls = []
        with patch("oops.commands.odoo.download.config", cfg_mock), \
                self._patch_dirs(community_dir, enterprise_dir, themes_dir), \
                patch("oops.commands.odoo.download.clone", side_effect=lambda *a, **kw: clone_calls.append(a)):
            result = self._runner().invoke(download_main, ["--version", "17.0"])
        cloned_dests = [c[1] for c in clone_calls]
        assert any(d.name == "themes" for d in cloned_dests)
        assert len(clone_calls) == 3
        assert result.exit_code == 0

    def test_no_themes_flag_skips_themes(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        clone_calls = []
        with patch("oops.commands.odoo.download.config", cfg_mock), \
                self._patch_dirs(community_dir), \
                patch("oops.commands.odoo.download.clone", side_effect=lambda *a, **kw: clone_calls.append(a)):
            self._runner().invoke(download_main, ["--version", "17.0", "--no-themes"])
        cloned_dests = [c[1] for c in clone_calls]
        assert not any(d.name == "themes" for d in cloned_dests)
        assert len(clone_calls) == 2

    def test_no_community_flag_skips_community(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        clone_calls = []
        with patch("oops.commands.odoo.download.config", cfg_mock), self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.download.clone", side_effect=lambda *a, **kw: clone_calls.append(a)
        ):
            self._runner().invoke(download_main, ["--version", "17.0", "--no-community"])
        cloned_dests = [c[1] for c in clone_calls]
        assert not any(d.name == "community" for d in cloned_dests)

    def test_themes_uses_themes_url_from_config(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        cfg_mock.odoo.themes_url = "git@github.com:my-fork/design-themes.git"
        clone_calls = []
        with patch("oops.commands.odoo.download.config", cfg_mock), \
                self._patch_dirs(community_dir), \
                patch("oops.commands.odoo.download.clone", side_effect=lambda *a, **kw: clone_calls.append(a)):
            self._runner().invoke(download_main, ["--version", "17.0", "--no-community", "--no-enterprise"])
        assert len(clone_calls) == 1
        url, dest, branch = clone_calls[0]
        assert url == "git@github.com:my-fork/design-themes.git"
        assert dest.name == "themes"
        assert branch == "17.0"

    def test_format_json_shape(self, tmp_path):
        """--format json produces valid JSON with metadata, warnings, repos keys."""
        community_dir = tmp_path / "17.0" / "community"
        cfg_mock = _make_config_mock(sources_dir=tmp_path)
        with patch("oops.commands.odoo.download.config", cfg_mock), \
                self._patch_dirs(community_dir), \
                patch("oops.commands.odoo.download.clone"):
            result = self._runner().invoke(
                download_main, ["--version", "17.0", "--no-enterprise", "--no-themes", "--format", "json"]
            )
        assert result.exit_code == 0
        # Strip any spinner/progress text that may precede the JSON payload.
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert "metadata" in data
        assert "warnings" in data
        assert "repos" in data
        assert data["metadata"]["command"] == "odoo download"
        assert "parameters" in data["metadata"]
        assert len(data["repos"]) == 1
        assert data["repos"][0]["action"] == "cloned"


# ---------------------------------------------------------------------------
# oops/commands/odoo/update.py
# ---------------------------------------------------------------------------


class TestUpdateCommand:
    def _runner(self):
        return CliRunner()

    def _patch_dirs(self, community_dir, enterprise_dir=None, themes_dir=None):
        from contextlib import ExitStack
        if enterprise_dir is None:
            enterprise_dir = community_dir.parent / "enterprise"
        if themes_dir is None:
            themes_dir = community_dir.parent / "themes"
        from oops.io.file import OdooSourcesDirs
        stack = ExitStack()
        stack.enter_context(patch(
            "oops.commands.odoo.update.get_odoo_sources_dirs",
            return_value=OdooSourcesDirs(
                community=community_dir,
                enterprise=enterprise_dir,
                themes=themes_dir,
            ),
        ))
        stack.enter_context(patch(
            "oops.commands.odoo.update.require_odoo_sources",
            return_value=[],
        ))
        return stack

    def test_version_normalization(self, tmp_path):
        community_dir = tmp_path / "19.0" / "community"
        community_dir.mkdir(parents=True)
        with self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["--version", "19", "--no-enterprise", "--no-themes"])
        mock_update.assert_called_once_with(community_dir, quiet=True)
        assert result.exit_code == 0

    def test_missing_sources_dir_raises_usage_error(self):
        from oops.core.exceptions import ConfigError
        with patch(
            "oops.commands.odoo.update.require_odoo_sources",
            side_effect=ConfigError("No base directory provided."),
        ):
            result = self._runner().invoke(update_main, ["--version", "17.0"])
        assert result.exit_code != 0
        assert "No base directory provided" in result.output

    def test_update_latest_called_without_date(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        with self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["--version", "17.0", "--no-enterprise", "--no-themes"])
        mock_update.assert_called_once_with(community_dir, quiet=True)
        assert result.exit_code == 0

    def test_update_at_date_called_with_date_flag(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        with self._patch_dirs(community_dir), patch(
            "oops.commands.odoo.update.update_at_date"
        ) as mock_uad:
            result = self._runner().invoke(
                update_main, ["--version", "17.0", "--date", "2024-01-15", "--no-enterprise", "--no-themes"]
            )
        mock_uad.assert_called_once_with(community_dir, "2024-01-15", quiet=True)
        assert result.exit_code == 0

    def test_enterprise_updated_by_default(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        themes_dir = tmp_path / "17.0" / "themes"
        community_dir.mkdir(parents=True)
        enterprise_dir.mkdir(parents=True)
        themes_dir.mkdir(parents=True)
        with self._patch_dirs(community_dir, enterprise_dir, themes_dir), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["--version", "17.0"])
        assert mock_update.call_count == 3
        updated_paths = {c.args[0] for c in mock_update.call_args_list}
        assert community_dir in updated_paths
        assert enterprise_dir in updated_paths
        assert themes_dir in updated_paths
        assert result.exit_code == 0

    def test_no_enterprise_no_themes_flag_updates_community_only(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        with self._patch_dirs(community_dir, enterprise_dir), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["--version", "17.0", "--no-enterprise", "--no-themes"])
        assert mock_update.call_count == 1
        assert mock_update.call_args.args[0] == community_dir
        assert result.exit_code == 0

    def test_dest_not_found_prints_warning_and_continues(self, tmp_path):
        """If dirs do not exist on disk, warn and continue (no crash, exit 0)."""
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        # Dirs intentionally not created — should trigger the not-found warning
        with self._patch_dirs(community_dir, enterprise_dir), patch(
            "oops.commands.odoo.update.update_latest"
        ) as mock_update:
            result = self._runner().invoke(update_main, ["--version", "17.0"])
        mock_update.assert_not_called()
        assert "not found" in result.output
        assert result.exit_code == 0

    def test_get_odoo_sources_dirs_called_with_version(self, tmp_path):
        """get_odoo_sources_dirs receives the normalised version string."""
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        from oops.io.file import OdooSourcesDirs
        themes_dir = community_dir.parent / "themes"
        with patch(
            "oops.commands.odoo.update.get_odoo_sources_dirs",
            return_value=OdooSourcesDirs(community=community_dir, enterprise=enterprise_dir, themes=themes_dir),
        ) as mock_dirs, patch("oops.commands.odoo.update.update_latest"), patch(
            "oops.commands.odoo.update.require_odoo_sources", return_value=[]
        ):
            self._runner().invoke(update_main, ["--version", "17.0", "--no-enterprise", "--no-themes"])
        mock_dirs.assert_called_once_with("17.0")

    def test_update_failure_exits_with_code_1(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        with self._patch_dirs(community_dir, enterprise_dir), patch(
            "oops.commands.odoo.update.update_latest",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            result = self._runner().invoke(update_main, ["--version", "17.0", "--no-themes"])
        assert result.exit_code == 1

    def test_themes_updated_by_default(self, tmp_path):
        community_dir = tmp_path / "17.0" / "community"
        enterprise_dir = tmp_path / "17.0" / "enterprise"
        themes_dir = tmp_path / "17.0" / "themes"
        for d in (community_dir, enterprise_dir, themes_dir):
            d.mkdir(parents=True)
        with self._patch_dirs(community_dir, enterprise_dir, themes_dir), \
                patch("oops.commands.odoo.update.update_latest") as mock_update:
            result = self._runner().invoke(update_main, ["--version", "17.0"])
        assert mock_update.call_count == 3
        updated = {c.args[0] for c in mock_update.call_args_list}
        assert themes_dir in updated
        assert result.exit_code == 0

    def test_themes_only_update(self, tmp_path):
        """--no-community --no-enterprise updates only themes."""
        themes_dir = tmp_path / "17.0" / "themes"
        themes_dir.mkdir(parents=True)
        with self._patch_dirs(
            tmp_path / "17.0" / "community",
            tmp_path / "17.0" / "enterprise",
            themes_dir,
        ), patch("oops.commands.odoo.update.update_latest") as mock_update:
            result = self._runner().invoke(update_main, ["--version", "17.0", "--no-community", "--no-enterprise"])
        assert mock_update.call_count == 1
        assert mock_update.call_args.args[0] == themes_dir
        assert result.exit_code == 0

    def test_themes_update_with_date(self, tmp_path):
        themes_dir = tmp_path / "17.0" / "themes"
        themes_dir.mkdir(parents=True)
        with self._patch_dirs(
            tmp_path / "17.0" / "community",
            tmp_path / "17.0" / "enterprise",
            themes_dir,
        ), patch("oops.commands.odoo.update.update_at_date") as mock_uad:
            result = self._runner().invoke(
                update_main,
                ["--version", "17.0", "--no-community", "--no-enterprise", "--date", "2024-06-30"],
            )
        mock_uad.assert_called_once_with(themes_dir, "2024-06-30", quiet=True)
        assert result.exit_code == 0

    def test_format_json_shape(self, tmp_path):
        """--format json produces valid JSON with metadata, warnings, repos keys."""
        community_dir = tmp_path / "17.0" / "community"
        community_dir.mkdir(parents=True)
        with self._patch_dirs(community_dir), \
                patch("oops.commands.odoo.update.update_latest"):
            result = self._runner().invoke(
                update_main, ["--version", "17.0", "--no-enterprise", "--no-themes", "--format", "json"]
            )
        assert result.exit_code == 0
        # Strip any spinner/progress text that may precede the JSON payload.
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert "metadata" in data
        assert "warnings" in data
        assert "repos" in data
        assert data["metadata"]["command"] == "odoo update"
        assert "parameters" in data["metadata"]
        assert len(data["repos"]) == 1
        assert data["repos"][0]["action"] == "updated"


# ---------------------------------------------------------------------------
# oops/commands/odoo/show.py
# ---------------------------------------------------------------------------


class TestShowCommand:
    def _runner(self):
        return CliRunner()

    def test_missing_sources_dir_raises_usage_error(self):
        from oops.core.exceptions import ConfigError
        with patch(
            "oops.commands.odoo.show.require_odoo_sources",
            side_effect=ConfigError("No base directory provided."),
        ):
            result = self._runner().invoke(show_main, [])
        assert result.exit_code != 0
        assert "No base directory provided" in result.output

    def test_sources_dir_does_not_exist(self, tmp_path):
        from oops.core.exceptions import OopsError
        with patch(
            "oops.commands.odoo.show.require_odoo_sources",
            side_effect=OopsError("Sources directory does not exist."),
        ):
            result = self._runner().invoke(show_main, [])
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_empty_sources_dir_reports_no_version_dirs(self, tmp_path):
        with patch("oops.commands.odoo.show.require_odoo_sources", return_value=[]):
            result = self._runner().invoke(show_main, [])
        assert result.exit_code == 0
        assert "No version directories found" in result.output

    def test_show_with_community_only(self, tmp_path):
        from oops.io.file import OdooSourcesStatus
        version_dir = tmp_path / "odoo-17"
        community_dir = version_dir / "community"
        community_dir.mkdir(parents=True)

        fake_info = "abc1234  2024-01-15 10:00:00 +0200"
        fake_status = [OdooSourcesStatus("odoo-17", True, False, False, version_dir)]

        def fake_repo_info(path):
            if path == community_dir:
                return fake_info
            return ""

        with patch("oops.commands.odoo.show.require_odoo_sources", return_value=fake_status), patch(
            "oops.commands.odoo.show.repo_info", side_effect=fake_repo_info
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "odoo-17" in result.output
        assert "abc1234" in result.output

    def test_show_with_community_and_enterprise(self, tmp_path):
        from oops.io.file import OdooSourcesStatus
        version_dir = tmp_path / "odoo-17"
        community_dir = version_dir / "community"
        enterprise_dir = version_dir / "enterprise"
        community_dir.mkdir(parents=True)
        enterprise_dir.mkdir(parents=True)

        community_info = "abc1234  2024-01-15 10:00:00 +0200"
        enterprise_info = "def5678  2024-01-15 10:00:00 +0200"
        fake_status = [OdooSourcesStatus("odoo-17", True, True, False, version_dir)]

        def fake_repo_info(path):
            if path == community_dir:
                return community_info
            if path == enterprise_dir:
                return enterprise_info
            return ""

        with patch("oops.commands.odoo.show.require_odoo_sources", return_value=fake_status), patch(
            "oops.commands.odoo.show.repo_info", side_effect=fake_repo_info
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "abc1234" in result.output
        assert "def5678" in result.output

    def test_version_dirs_with_no_repos_shows_no_checkouts(self, tmp_path):
        from oops.io.file import OdooSourcesStatus
        version_dir = tmp_path / "17.0"
        version_dir.mkdir()
        fake_status = [OdooSourcesStatus("17.0", False, False, False, version_dir)]

        with patch("oops.commands.odoo.show.require_odoo_sources", return_value=fake_status), patch(
            "oops.commands.odoo.show.repo_info", return_value=""
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "17.0" in result.output

    def test_multiple_version_dirs_shown(self, tmp_path):
        from oops.io.file import OdooSourcesStatus
        for version in ("odoo-17", "odoo-18"):
            community_dir = tmp_path / version / "community"
            community_dir.mkdir(parents=True)
        fake_status = [
            OdooSourcesStatus("odoo-17", True, False, False, tmp_path / "odoo-17"),
            OdooSourcesStatus("odoo-18", True, False, False, tmp_path / "odoo-18"),
        ]

        def fake_repo_info(path):
            if path.name == "community":
                return "hash  2024-01-01 +0000"
            return ""

        with patch("oops.commands.odoo.show.require_odoo_sources", return_value=fake_status), patch(
            "oops.commands.odoo.show.repo_info", side_effect=fake_repo_info
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "odoo-17" in result.output
        assert "odoo-18" in result.output

    def test_show_with_themes(self, tmp_path):
        """Themes are displayed alongside community and enterprise."""
        from oops.io.file import OdooSourcesStatus
        version_dir = tmp_path / "odoo-17"
        themes_dir = version_dir / "themes"
        themes_dir.mkdir(parents=True)

        themes_info = "9876abc  2024-02-01 12:00:00 +0200"
        fake_status = [OdooSourcesStatus("odoo-17", False, False, True, version_dir)]

        def fake_repo_info(path):
            if path == themes_dir:
                return themes_info
            return ""

        with patch("oops.commands.odoo.show.require_odoo_sources", return_value=fake_status), patch(
            "oops.commands.odoo.show.repo_info", side_effect=fake_repo_info
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "9876abc" in result.output
        assert "Themes" in result.output

    def test_show_includes_summary_panel(self, tmp_path):
        from oops.io.file import OdooSourcesStatus
        version_dir = tmp_path / "odoo-17"
        community_dir = version_dir / "community"
        community_dir.mkdir(parents=True)
        fake_status = [OdooSourcesStatus("odoo-17", True, False, False, version_dir)]

        def fake_repo_info(path):
            if path == community_dir:
                return "abc1234  2024-01-15 10:00:00 +0200"
            return ""

        with patch("oops.commands.odoo.show.require_odoo_sources", return_value=fake_status), patch(
            "oops.commands.odoo.show.repo_info", side_effect=fake_repo_info
        ):
            result = self._runner().invoke(show_main, [])

        assert result.exit_code == 0
        assert "Summary" in result.output
        assert "Version" in result.output


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

    def test_apply_themes_url(self):
        from oops.core.config import Config

        cfg = Config()
        _apply(cfg, {"odoo": {"themes_url": "git@github.com:my-fork/design-themes.git"}})
        assert cfg.odoo.themes_url == "git@github.com:my-fork/design-themes.git"

    def test_defaults(self):
        cfg = OdooConfig()
        assert cfg.sources_dir is None
        assert cfg.community_url == "git@github.com:odoo/odoo.git"
        assert cfg.enterprise_url == "git@github.com:odoo/enterprise.git"
        assert cfg.themes_url == "git@github.com:odoo/design-themes.git"
