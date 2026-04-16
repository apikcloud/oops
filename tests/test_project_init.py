# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_project_init.py — tests/test_project_init.py

"""Tests for oops/commands/project/init.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.project.init import main as init_main

_COMPOSE = "compose-content"


def _make_image_info(major_version: float = 17.0, image: str = "registry/odoo:17.0"):
    info = MagicMock()
    info.major_version = major_version
    info.image = image
    return info


def _make_local_repo(tmp_path: Path):
    return MagicMock(), tmp_path


# ---------------------------------------------------------------------------
# TestProjectInit — happy path
# ---------------------------------------------------------------------------


class TestProjectInit:
    def _run(self, tmp_path, args=None, major_version=17.0):
        """Invoke init with standard mocks; return (result, mock_workspace)."""
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(major_version),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ), patch(
            "oops.commands.project.init.run"
        ), patch(
            "oops.commands.misc.create_workspace.main"
        ) as mock_ws:
            result = runner.invoke(init_main, args or [])
        return result, mock_ws

    def test_creates_compose_file(self, tmp_path):
        result, _ = self._run(tmp_path)
        assert result.exit_code == 0, result.output
        assert (tmp_path / "docker-compose.yml").read_text() == _COMPOSE

    def test_creates_odoo_conf(self, tmp_path):
        result, _ = self._run(tmp_path)
        assert result.exit_code == 0
        assert (tmp_path / ".config" / "odoo.conf").exists()

    def test_creates_config_dir(self, tmp_path):
        self._run(tmp_path)
        assert (tmp_path / ".config").is_dir()

    def test_success_output_mentions_compose(self, tmp_path):
        result, _ = self._run(tmp_path)
        assert "docker-compose.yml" in result.output

    def test_success_output_mentions_conf(self, tmp_path):
        result, _ = self._run(tmp_path)
        assert "odoo.conf" in result.output

    def test_chmod_run_on_config_dir(self, tmp_path):
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ), patch(
            "oops.commands.project.init.run"
        ) as mock_run, patch(
            "oops.commands.misc.create_workspace.main"
        ):
            runner.invoke(init_main, [])
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert "chmod" in cmd
        assert "777" in cmd


# ---------------------------------------------------------------------------
# TestProjectInitWorkspace — --without-workspace flag
# ---------------------------------------------------------------------------


class TestProjectInitWorkspace:
    def test_workspace_invoked_by_default(self, tmp_path):
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ), patch(
            "oops.commands.project.init.run"
        ), patch(
            "oops.commands.misc.create_workspace.main"
        ) as mock_ws:
            result = runner.invoke(init_main, [])
        assert result.exit_code == 0, result.output
        mock_ws.assert_called_once()

    def test_without_workspace_skips_workspace(self, tmp_path):
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ), patch(
            "oops.commands.project.init.run"
        ), patch(
            "oops.commands.misc.create_workspace.main"
        ) as mock_ws:
            result = runner.invoke(init_main, ["--without-workspace"])
        assert result.exit_code == 0
        mock_ws.assert_not_called()

    def test_include_sources_forwarded_to_workspace(self, tmp_path):
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ), patch(
            "oops.commands.project.init.run"
        ), patch(
            "oops.commands.misc.create_workspace.main"
        ) as mock_ws:
            result = runner.invoke(init_main, ["--include-sources"])
        assert result.exit_code == 0, result.output
        mock_ws.assert_called_once()
        assert mock_ws.call_args.kwargs.get("include_sources") is True

    def test_include_sources_defaults_to_false(self, tmp_path):
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ), patch(
            "oops.commands.project.init.run"
        ), patch(
            "oops.commands.misc.create_workspace.main"
        ) as mock_ws:
            result = runner.invoke(init_main, [])
        assert result.exit_code == 0, result.output
        mock_ws.assert_called_once()
        assert mock_ws.call_args.kwargs.get("include_sources") is False


# ---------------------------------------------------------------------------
# TestProjectInitBuildCompose — odoo_version and options forwarding
# ---------------------------------------------------------------------------


class TestProjectInitBuildCompose:
    def _run_with_mock_build(self, tmp_path, args=None, major_version=17.0):
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(major_version),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ) as mock_build, patch(
            "oops.commands.project.init.run"
        ), patch(
            "oops.commands.misc.create_workspace.main"
        ):
            runner.invoke(init_main, args or [])
        return mock_build

    def test_odoo_version_forwarded_to_build_compose(self, tmp_path):
        mock_build = self._run_with_mock_build(tmp_path, major_version=19.0)
        assert mock_build.call_args.kwargs["odoo_version"] == 19.0

    def test_port_option_forwarded(self, tmp_path):
        mock_build = self._run_with_mock_build(tmp_path, args=["--port", "8080"])
        assert mock_build.call_args.kwargs["port"] == 8080

    def test_with_maildev_forwarded(self, tmp_path):
        mock_build = self._run_with_mock_build(tmp_path, args=["--with-maildev"])
        assert mock_build.call_args.kwargs["with_maildev"] is True

    def test_with_sftp_forwarded(self, tmp_path):
        mock_build = self._run_with_mock_build(tmp_path, args=["--with-sftp"])
        assert mock_build.call_args.kwargs["with_sftp"] is True

    def test_no_dev_forwarded(self, tmp_path):
        mock_build = self._run_with_mock_build(tmp_path, args=["--no-dev"])
        assert mock_build.call_args.kwargs["dev"] is False


# ---------------------------------------------------------------------------
# TestProjectInitErrors — error and overwrite handling
# ---------------------------------------------------------------------------


class TestProjectInitErrors:
    def test_version_error_exits_with_message(self, tmp_path):
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            side_effect=FileNotFoundError("missing"),
        ), patch("oops.commands.project.init.run"):
            result = runner.invoke(init_main, [])
        assert result.exit_code != 0
        assert "Could not determine Odoo image" in result.output

    def test_value_error_exits_with_message(self, tmp_path):
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            side_effect=ValueError("bad version"),
        ), patch("oops.commands.project.init.run"):
            result = runner.invoke(init_main, [])
        assert result.exit_code != 0
        assert "Could not determine Odoo image" in result.output

    def test_overwrite_prompt_aborts_without_confirmation(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text("old")
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ), patch("oops.commands.project.init.run"):
            result = runner.invoke(init_main, [])
        assert result.exit_code != 0
        assert (tmp_path / "docker-compose.yml").read_text() == "old"

    def test_overwrite_confirmed_rewrites_compose(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text("old")
        runner = CliRunner()
        with patch(
            "oops.commands.project.init.get_local_repo",
            return_value=_make_local_repo(tmp_path),
        ), patch(
            "oops.commands.project.init.parse_odoo_version",
            return_value=_make_image_info(),
        ), patch(
            "oops.commands.project.init.build_compose",
            return_value=_COMPOSE,
        ), patch(
            "oops.commands.project.init.run"
        ), patch(
            "oops.commands.misc.create_workspace.main"
        ):
            result = runner.invoke(init_main, [], input="y\n")
        assert result.exit_code == 0
        assert (tmp_path / "docker-compose.yml").read_text() == _COMPOSE
