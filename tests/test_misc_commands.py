# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_misc_commands.py — tests/test_misc_commands.py

"""Tests for oops/commands/misc/create_workspace.py and build_global.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner
from oops.commands.misc.create_workspace import main as workspace_main
from oops.core.models import Result
from oops.io.file import OdooSourcesDirs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_mock(odoo_version=None):
    cfg = MagicMock()
    cfg.default_timeout = 60
    cfg.manifest = MagicMock()
    cfg.manifest.odoo_version = odoo_version
    cfg.project = MagicMock()
    cfg.project.file_odoo_version = "odoo_version.txt"
    return cfg


def _make_version_info(major_version=17.0, enterprise=False):
    info = MagicMock()
    info.major_version = major_version
    info.enterprise = enterprise
    return info


def _make_local_repo(tmp_path: Path):
    return MagicMock(), tmp_path


def _source_dirs(base: Path, version: str, create: bool = True) -> OdooSourcesDirs:
    """Return an OdooSourcesDirs under base/version/, optionally creating dirs."""
    community = base / version / "community"
    enterprise = base / version / "enterprise"
    themes = base / version / "themes"
    if create:
        community.mkdir(parents=True, exist_ok=True)
        enterprise.mkdir(parents=True, exist_ok=True)
        themes.mkdir(parents=True, exist_ok=True)
    return OdooSourcesDirs(community=community, enterprise=enterprise, themes=themes)


# ---------------------------------------------------------------------------
# TestCreateWorkspace — normal paths
# ---------------------------------------------------------------------------


class TestCreateWorkspace:
    def _runner(self):
        return CliRunner()

    def _invoke(self, tmp_path, version_info=None, args=None, dirs=None):
        if version_info is None:
            version_info = _make_version_info()
        if dirs is None:
            dirs = _source_dirs(tmp_path / "sources", str(version_info.major_version))
        cfg = _make_config_mock()
        with patch("oops.commands.misc.create_workspace.config", cfg), patch(
            "oops.commands.misc.create_workspace.require_repository",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.create_workspace.parse_odoo_version",
            return_value=version_info,
        ), patch(
            "oops.commands.misc.create_workspace.get_odoo_sources_dirs",
            return_value=dirs,
        ):
            result = self._runner().invoke(workspace_main, args or [])
        return result

    def test_workspace_file_written_at_repo_root(self, tmp_path):
        result = self._invoke(tmp_path)
        assert result.exit_code == 0, result.output
        assert (tmp_path / f"{tmp_path.name}.code-workspace").exists()

    def test_workspace_file_name_matches_repo_name(self, tmp_path):
        self._invoke(tmp_path)
        assert (tmp_path / f"{tmp_path.name}.code-workspace").exists()

    def test_workspace_content_has_correct_structure(self, tmp_path):
        self._invoke(tmp_path)
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        assert data["folders"] == [{"path": "."}]
        assert "settings" in data
        assert "python.analysis.extraPaths" in data["settings"]
        assert "python.autoComplete.extraPaths" in data["settings"]

    def test_extra_paths_include_community(self, tmp_path):
        sources = tmp_path / "sources"
        dirs = _source_dirs(sources, "17.0")
        self._invoke(tmp_path, dirs=dirs)
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        assert str(dirs.community) in data["settings"]["python.analysis.extraPaths"]

    def test_extra_paths_include_enterprise_when_enterprise(self, tmp_path):
        sources = tmp_path / "sources"
        dirs = _source_dirs(sources, "17.0")
        info = _make_version_info(enterprise=True)
        self._invoke(tmp_path, version_info=info, dirs=dirs)
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        extra = data["settings"]["python.analysis.extraPaths"]
        assert str(dirs.community) in extra
        assert str(dirs.enterprise) in extra

    def test_success_message_contains_version(self, tmp_path):
        result = self._invoke(tmp_path, version_info=_make_version_info(19.0))
        assert "19.0" in result.output

    def test_workspace_file_ends_with_newline(self, tmp_path):
        self._invoke(tmp_path)
        assert (tmp_path / f"{tmp_path.name}.code-workspace").read_text().endswith("\n")

    def test_extra_paths_include_themes_by_default(self, tmp_path):
        sources = tmp_path / "sources"
        dirs = _source_dirs(sources, "17.0")
        self._invoke(tmp_path, dirs=dirs)
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        assert str(dirs.themes) in data["settings"]["python.analysis.extraPaths"]

    def test_no_themes_flag_excludes_themes(self, tmp_path):
        sources = tmp_path / "sources"
        dirs = _source_dirs(sources, "17.0")
        self._invoke(tmp_path, dirs=dirs, args=["--no-themes"])
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        assert str(dirs.themes) not in data["settings"]["python.analysis.extraPaths"]


# ---------------------------------------------------------------------------
# TestCreateWorkspaceOptions — --output
# ---------------------------------------------------------------------------


class TestCreateWorkspaceOptions:
    def _runner(self):
        return CliRunner()

    def test_output_option_writes_to_custom_path(self, tmp_path):
        custom_out = tmp_path / "my.code-workspace"
        sources = tmp_path / "sources"
        dirs = _source_dirs(sources, "17.0")
        cfg = _make_config_mock()
        with patch("oops.commands.misc.create_workspace.config", cfg), patch(
            "oops.commands.misc.create_workspace.require_repository",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.create_workspace.parse_odoo_version",
            return_value=_make_version_info(),
        ), patch(
            "oops.commands.misc.create_workspace.get_odoo_sources_dirs",
            return_value=dirs,
        ):
            result = self._runner().invoke(workspace_main, ["--output", str(custom_out)])
        assert result.exit_code == 0
        assert custom_out.exists()

    def test_no_sources_dir_raises_usage_error(self, tmp_path):
        cfg = _make_config_mock()
        with patch("oops.commands.misc.create_workspace.config", cfg), patch(
            "oops.commands.misc.create_workspace.require_repository",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.create_workspace.parse_odoo_version",
            return_value=_make_version_info(),
        ), patch(
            "oops.commands.misc.create_workspace.get_odoo_sources_dirs",
            side_effect=click.UsageError("No base directory"),
        ):
            result = self._runner().invoke(workspace_main, [])
        assert result.exit_code != 0
        assert "No base directory" in result.output


# ---------------------------------------------------------------------------
# TestCreateWorkspaceVersionFallback — version resolution
# ---------------------------------------------------------------------------


class TestCreateWorkspaceVersionFallback:
    def _runner(self):
        return CliRunner()

    def test_version_from_file(self, tmp_path):
        sources = tmp_path / "sources"
        dirs = _source_dirs(sources, "18.0")
        cfg = _make_config_mock()
        with patch("oops.commands.misc.create_workspace.config", cfg), patch(
            "oops.commands.misc.create_workspace.require_repository",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.create_workspace.parse_odoo_version",
            return_value=_make_version_info(18.0),
        ), patch(
            "oops.commands.misc.create_workspace.get_odoo_sources_dirs",
            return_value=dirs,
        ):
            result = self._runner().invoke(workspace_main, [])
        assert result.exit_code == 0
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        assert str(dirs.community) in data["settings"]["python.analysis.extraPaths"]

    def test_fallback_to_config_manifest_odoo_version(self, tmp_path):
        sources = tmp_path / "sources"
        dirs = _source_dirs(sources, "16.0")
        cfg = _make_config_mock(odoo_version="16.0")
        with patch("oops.commands.misc.create_workspace.config", cfg), patch(
            "oops.commands.misc.create_workspace.require_repository",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.create_workspace.parse_odoo_version",
            side_effect=ValueError("no version file"),
        ), patch(
            "oops.commands.misc.create_workspace.get_odoo_sources_dirs",
            return_value=dirs,
        ):
            result = self._runner().invoke(workspace_main, [])
        assert result.exit_code == 0
        data = json.loads((tmp_path / f"{tmp_path.name}.code-workspace").read_text())
        assert str(dirs.community) in data["settings"]["python.analysis.extraPaths"]

    def test_fallback_emits_warning(self, tmp_path):
        sources = tmp_path / "sources"
        dirs = _source_dirs(sources, "16.0")
        cfg = _make_config_mock(odoo_version="16.0")
        with patch("oops.commands.misc.create_workspace.config", cfg), patch(
            "oops.commands.misc.create_workspace.require_repository",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.create_workspace.parse_odoo_version",
            side_effect=ValueError("no version file"),
        ), patch(
            "oops.commands.misc.create_workspace.get_odoo_sources_dirs",
            return_value=dirs,
        ):
            result = self._runner().invoke(workspace_main, [])
        assert "Could not read version" in result.output

    def test_no_version_anywhere_exits_with_error(self, tmp_path):
        cfg = _make_config_mock(odoo_version=None)
        with patch("oops.commands.misc.create_workspace.config", cfg), patch(
            "oops.commands.misc.create_workspace.require_repository",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.create_workspace.parse_odoo_version",
            side_effect=ValueError("no version file"),
        ):
            result = self._runner().invoke(workspace_main, [])
        assert result.exit_code != 0
        assert "manifest.odoo_version" in result.output


# ---------------------------------------------------------------------------
# TestCreateWorkspaceDownload — --without-download and auto-download chaining
# ---------------------------------------------------------------------------


class TestCreateWorkspaceDownload:
    def _runner(self):
        return CliRunner()

    def _invoke(self, tmp_path, version_info, sources_exist=True, args=None):
        sources = tmp_path / "sources"
        version_str = str(version_info.major_version)
        dirs = _source_dirs(sources, version_str, create=sources_exist)
        cfg = _make_config_mock()
        with patch("oops.commands.misc.create_workspace.config", cfg), patch(
            "oops.commands.misc.create_workspace.require_repository",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.misc.create_workspace.parse_odoo_version",
            return_value=version_info,
        ), patch(
            "oops.commands.misc.create_workspace.get_odoo_sources_dirs",
            return_value=dirs,
        ), patch(
            "oops.commands.odoo.download.main"
        ) as mock_dl:
            result = self._runner().invoke(workspace_main, args or [])
        return result, mock_dl

    def test_no_download_when_sources_present(self, tmp_path):
        result, mock_dl = self._invoke(tmp_path, _make_version_info(17.0), sources_exist=True)
        assert result.exit_code == 0
        mock_dl.assert_not_called()

    def test_download_triggered_when_sources_missing(self, tmp_path):
        result, mock_dl = self._invoke(tmp_path, _make_version_info(17.0), sources_exist=False)
        assert result.exit_code == 0
        mock_dl.assert_called_once()

    def test_download_called_with_correct_version(self, tmp_path):
        _, mock_dl = self._invoke(tmp_path, _make_version_info(18.0), sources_exist=False)
        assert mock_dl.call_args.kwargs.get("version") == "18.0"

    def test_download_called_with_update_and_enterprise(self, tmp_path):
        info = _make_version_info(17.0, enterprise=True)
        _, mock_dl = self._invoke(tmp_path, info, sources_exist=False)
        kwargs = mock_dl.call_args.kwargs
        assert kwargs.get("do_update") is True
        assert kwargs.get("with_enterprise") is True

    def test_without_download_warns_when_sources_missing(self, tmp_path):
        result, mock_dl = self._invoke(
            tmp_path, _make_version_info(17.0), sources_exist=False, args=["--without-download"]
        )
        assert result.exit_code == 0
        assert "missing" in result.output.lower() or "check" in result.output.lower()
        mock_dl.assert_not_called()

    def test_without_download_still_writes_workspace_file(self, tmp_path):
        result, _ = self._invoke(
            tmp_path, _make_version_info(17.0), sources_exist=False, args=["--without-download"]
        )
        assert result.exit_code == 0
        assert (tmp_path / f"{tmp_path.name}.code-workspace").exists()

    def test_download_called_with_themes_flag(self, tmp_path):
        _, mock_dl = self._invoke(tmp_path, _make_version_info(17.0), sources_exist=False)
        assert mock_dl.call_args.kwargs.get("with_themes") is True

    def test_download_called_without_themes_when_no_themes(self, tmp_path):
        _, mock_dl = self._invoke(
            tmp_path, _make_version_info(17.0), sources_exist=False, args=["--no-themes"]
        )
        assert mock_dl.call_args.kwargs.get("with_themes") is False


# ---------------------------------------------------------------------------
# TestBuildKb — oops misc build-kb regression tests
# ---------------------------------------------------------------------------


class TestBuildKb:
    """Smoke / regression tests for oops misc build-kb."""

    def _runner(self):
        return CliRunner()

    def _invoke(self, tmp_path, version="17.0", with_enterprise=True, with_themes=True):
        sources = tmp_path / "sources"
        community = sources / version / "community"
        enterprise = sources / version / "enterprise"
        themes = sources / version / "themes"
        community.mkdir(parents=True, exist_ok=True)
        if with_enterprise:
            enterprise.mkdir(parents=True, exist_ok=True)
        if with_themes:
            themes.mkdir(parents=True, exist_ok=True)
        dirs = OdooSourcesDirs(community=community, enterprise=enterprise, themes=themes)
        cache_dir = tmp_path / "cache"

        from oops.commands.misc.build_global import main as build_kb_main

        with patch(
            "oops.commands.misc.build_global.get_odoo_sources_dirs",
            return_value=dirs,
        ), patch(
            "oops.commands.misc.build_global.odoo_addons_roots",
            return_value=[community],
        ), patch(
            "oops.commands.misc.build_global.scan_tier",
            return_value=Result(
                data={"modules": {}, "symbols": [], "field_refs": [], "model_origins": []}
            ),
        ) as mock_scan, patch(
            "oops.commands.misc.build_global._resolve_prototype_roles"
        ), patch(
            "oops.commands.misc.build_global.write_global_kb",
            return_value=Result(
                data={
                    "file": tmp_path / "kb.db",
                    "modules": 0,
                    "symbols": 0,
                    "fields": 0,
                    "methods": 0,
                    "field_refs": 0,
                    "model_origins": 0,
                }
            ),
        ) as mock_write:
            result = self._runner().invoke(
                build_kb_main,
                ["--version", version, "--cache-dir", str(cache_dir)],
            )
        return result, mock_scan, mock_write

    def test_happy_path_runs_to_completion(self, tmp_path):
        result, _, mock_write = self._invoke(tmp_path)
        assert result.exit_code == 0, result.output
        mock_write.assert_called_once()

    def test_scans_community_enterprise_themes_when_all_present(self, tmp_path):
        result, mock_scan, _ = self._invoke(tmp_path)
        assert result.exit_code == 0, result.output
        tiers = [call.args[1] for call in mock_scan.call_args_list]
        assert "odoo" in tiers
        assert "enterprise" in tiers
        assert "themes" in tiers

    def test_skips_enterprise_when_missing(self, tmp_path):
        result, mock_scan, _ = self._invoke(tmp_path, with_enterprise=False)
        assert result.exit_code == 0, result.output
        tiers = [call.args[1] for call in mock_scan.call_args_list]
        assert "enterprise" not in tiers

    def test_skips_themes_when_missing(self, tmp_path):
        result, mock_scan, _ = self._invoke(tmp_path, with_themes=False)
        assert result.exit_code == 0, result.output
        tiers = [call.args[1] for call in mock_scan.call_args_list]
        assert "themes" not in tiers

    def test_writes_sources_map_with_themes_when_present(self, tmp_path):
        _, _, mock_write = self._invoke(tmp_path)
        sources = mock_write.call_args.kwargs["sources"]
        assert "odoo" in sources
        assert "enterprise" in sources
        assert "themes" in sources
