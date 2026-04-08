# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: test_misc_commands.py — tests/test_misc_commands.py

"""Tests for oops/commands/misc/workspace.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from oops.commands.misc.workspace import main as workspace_main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_mock(sources_dir=None, odoo_version=None):
    cfg = MagicMock()
    cfg.default_timeout = 60
    cfg.odoo = MagicMock()
    cfg.odoo.sources_dir = sources_dir
    cfg.manifest = MagicMock()
    cfg.manifest.odoo_version = odoo_version
    cfg.project = MagicMock()
    cfg.project.file_odoo_version = "odoo_version.txt"
    return cfg


def _make_version_info(major_version=17.0):
    info = MagicMock()
    info.major_version = major_version
    return info


def _make_local_repo(tmp_path: Path):
    repo = MagicMock()
    return repo, tmp_path


# ---------------------------------------------------------------------------
# TestCreateWorkspace — normal paths
# ---------------------------------------------------------------------------


class TestCreateWorkspace:
    def _runner(self):
        return CliRunner()

    def test_workspace_file_written_at_repo_root(self, tmp_path):
        cfg = _make_config_mock(sources_dir=tmp_path / "sources")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(17.0),
        ):
            result = self._runner().invoke(workspace_main, [])
        assert result.exit_code == 0
        expected_file = tmp_path / f"{tmp_path.name}.code-workspace"
        assert expected_file.exists()

    def test_workspace_file_name_matches_repo_name(self, tmp_path):
        cfg = _make_config_mock(sources_dir=tmp_path / "sources")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(17.0),
        ):
            self._runner().invoke(workspace_main, [])
        assert (tmp_path / f"{tmp_path.name}.code-workspace").exists()

    def test_workspace_content_has_correct_structure(self, tmp_path):
        sources = tmp_path / "sources"
        cfg = _make_config_mock(sources_dir=sources)
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(17.0),
        ):
            self._runner().invoke(workspace_main, [])
        workspace_file = tmp_path / f"{tmp_path.name}.code-workspace"
        data = json.loads(workspace_file.read_text())
        assert data["folders"] == [{"path": "."}]
        assert "settings" in data
        assert "python.analysis.extraPaths" in data["settings"]
        assert "python.autoComplete.extraPaths" in data["settings"]

    def test_extra_paths_point_to_community_and_enterprise(self, tmp_path):
        sources = tmp_path / "sources"
        cfg = _make_config_mock(sources_dir=sources)
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(17.0),
        ):
            self._runner().invoke(workspace_main, [])
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        extra_paths = data["settings"]["python.analysis.extraPaths"]
        assert str(sources / "17.0" / "community") in extra_paths
        assert str(sources / "17.0" / "enterprise") in extra_paths

    def test_success_message_contains_version(self, tmp_path):
        cfg = _make_config_mock(sources_dir=tmp_path / "sources")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(19.0),
        ):
            result = self._runner().invoke(workspace_main, [])
        assert "19.0" in result.output

    def test_workspace_file_ends_with_newline(self, tmp_path):
        cfg = _make_config_mock(sources_dir=tmp_path / "sources")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(17.0),
        ):
            self._runner().invoke(workspace_main, [])
        workspace_file = tmp_path / f"{tmp_path.name}.code-workspace"
        assert workspace_file.read_text().endswith("\n")


# ---------------------------------------------------------------------------
# TestCreateWorkspaceOptions — --base-dir and --output
# ---------------------------------------------------------------------------


class TestCreateWorkspaceOptions:
    def _runner(self):
        return CliRunner()

    def test_base_dir_option_overrides_config(self, tmp_path):
        custom_sources = tmp_path / "custom"
        cfg = _make_config_mock(sources_dir=tmp_path / "config-sources")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(17.0),
        ):
            self._runner().invoke(workspace_main, ["--base-dir", str(custom_sources)])
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        extra_paths = data["settings"]["python.analysis.extraPaths"]
        assert str(custom_sources / "17.0" / "community") in extra_paths

    def test_output_option_writes_to_custom_path(self, tmp_path):
        custom_out = tmp_path / "my.code-workspace"
        cfg = _make_config_mock(sources_dir=tmp_path / "sources")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(17.0),
        ):
            result = self._runner().invoke(workspace_main, ["--output", str(custom_out)])
        assert result.exit_code == 0
        assert custom_out.exists()

    def test_no_sources_dir_and_no_base_dir_raises_usage_error(self, tmp_path):
        cfg = _make_config_mock(sources_dir=None)
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(17.0),
        ):
            result = self._runner().invoke(workspace_main, [])
        assert result.exit_code != 0
        assert "No base directory" in result.output


# ---------------------------------------------------------------------------
# TestCreateWorkspaceVersionError — version resolution
# ---------------------------------------------------------------------------


class TestCreateWorkspaceVersionFallback:
    def _runner(self):
        return CliRunner()

    def test_version_from_file(self, tmp_path):
        cfg = _make_config_mock(sources_dir=tmp_path / "sources")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            return_value=_make_version_info(18.0),
        ):
            result = self._runner().invoke(workspace_main, [])
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        assert str(tmp_path / "sources" / "18.0" / "community") in (
            data["settings"]["python.analysis.extraPaths"]
        )

    def test_fallback_to_config_manifest_odoo_version(self, tmp_path):
        cfg = _make_config_mock(sources_dir=tmp_path / "sources", odoo_version="16.0")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            side_effect=ValueError("no version file"),
        ):
            result = self._runner().invoke(workspace_main, [])
        assert result.exit_code == 0
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        assert str(tmp_path / "sources" / "16.0" / "community") in (
            data["settings"]["python.analysis.extraPaths"]
        )

    def test_fallback_emits_warning(self, tmp_path):
        cfg = _make_config_mock(sources_dir=tmp_path / "sources", odoo_version="16.0")
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            side_effect=ValueError("no version file"),
        ):
            result = self._runner().invoke(workspace_main, [])
        assert "Could not read version" in result.output

    def test_no_version_anywhere_exits_with_error(self, tmp_path):
        cfg = _make_config_mock(sources_dir=tmp_path / "sources", odoo_version=None)
        with patch("oops.commands.misc.workspace.config", cfg), patch(
            "oops.commands.misc.workspace.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.workspace.parse_odoo_version",
            side_effect=ValueError("no version file"),
        ):
            result = self._runner().invoke(workspace_main, [])
        assert result.exit_code != 0
        assert "manifest.odoo_version" in result.output
