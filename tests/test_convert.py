"""Tests for oops.commands.project.convert."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.project.convert import main
from oops.core.models import ImageInfo


def _make_config(
    remote_url="https://example.com/repo.git",
    branch="main",
    files=None,
    mandatory_files=None,
    recommended_files=None,
    file_odoo_version="odoo_version.txt",
):
    cfg = MagicMock()
    cfg.sync.remote_url = remote_url
    cfg.sync.branch = branch
    cfg.sync.files = files if files is not None else ["requirements.txt", "packages.txt"]
    cfg.project.mandatory_files = mandatory_files if mandatory_files is not None else {
        "requirements.txt",
        "packages.txt",
        "odoo_version.txt",
    }
    cfg.project.recommended_files = recommended_files if recommended_files is not None else set()
    cfg.project.file_odoo_version = file_odoo_version
    return cfg


def _make_image(tag="apik/odoo:19.0-20250601-enterprise", release=None):
    return ImageInfo(
        image=tag,
        registry="apik",
        repository="odoo",
        major_version=19.0,
        release=release or date(2025, 6, 1),
        enterprise=True,
        collection="production",
    )


def _make_local_repo(tmp_path):
    mock_repo = MagicMock()
    mock_repo.working_tree_dir = str(tmp_path)
    return mock_repo


# ---------------------------------------------------------------------------
# Bootstrap guard
# ---------------------------------------------------------------------------


class TestBootstrapGuard:
    def test_already_bootstrapped_exits_0(self, tmp_path):
        """All mandatory files present → EarlyExit (exit 0)."""
        for f in ["requirements.txt", "packages.txt", "odoo_version.txt"]:
            (tmp_path / f).write_text("")
        cfg = _make_config()
        runner = CliRunner()
        with patch("oops.commands.project.convert.config", cfg), patch(
            "oops.commands.project.convert.require_repository",
            return_value=(_make_local_repo(tmp_path), tmp_path),
        ):
            result = runner.invoke(main, ["-v", "19"])
        assert result.exit_code == 0
        assert "bootstrapped" in result.output.lower()


# ---------------------------------------------------------------------------
# Config guards
# ---------------------------------------------------------------------------


class TestConfigGuards:
    def _base_invoke(self, tmp_path, cfg_override):
        runner = CliRunner()
        with patch("oops.commands.project.convert.config", cfg_override), patch(
            "oops.commands.project.convert.require_repository",
            return_value=(_make_local_repo(tmp_path), tmp_path),
        ), patch("oops.commands.project.convert.fetch_project_files"):
            return runner.invoke(main, ["-v", "19"])

    def test_missing_remote_url(self, tmp_path):
        result = self._base_invoke(tmp_path, _make_config(remote_url=None))
        assert result.exit_code != 0
        assert "sync.remote_url" in result.output

    def test_missing_branch(self, tmp_path):
        result = self._base_invoke(tmp_path, _make_config(branch=None))
        assert result.exit_code != 0
        assert "sync.branch" in result.output


# ---------------------------------------------------------------------------
# --release validation
# ---------------------------------------------------------------------------


class TestReleaseValidation:
    def test_invalid_release_format_exits_2(self, tmp_path):
        runner = CliRunner()
        cfg = _make_config()
        with patch("oops.commands.project.convert.config", cfg), patch(
            "oops.commands.project.convert.require_repository",
            return_value=(_make_local_repo(tmp_path), tmp_path),
        ):
            result = runner.invoke(main, ["-v", "19", "-r", "2025-13-40"])
        assert result.exit_code == 2
        assert "YYYY-MM-DD" in result.output


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_creates_bootstrap_commit(self, tmp_path):
        cfg = _make_config(
            files=["requirements.txt"],
            mandatory_files={"requirements.txt", "odoo_version.txt"},
        )
        image = _make_image()
        runner = CliRunner()
        with patch("oops.commands.project.convert.config", cfg), patch(
            "oops.commands.project.convert.require_repository",
            return_value=(_make_local_repo(tmp_path), tmp_path),
        ), patch("oops.commands.project.convert.fetch_project_files"), patch(
            "oops.commands.project.convert.copy_project_files",
            return_value=["requirements.txt"],
        ), patch(
            "oops.commands.project.convert.find_available_images",
            return_value=[image],
        ), patch(
            "oops.commands.project.convert.prompt_select",
            return_value=f"{image.image}   {image.release.isoformat()}  Δ0d",
        ), patch(
            "oops.commands.project.convert.write_text_file"
        ), patch(
            "oops.commands.project.convert.commit"
        ) as mock_commit:
            result = runner.invoke(main, ["-v", "19"])

        assert result.exit_code == 0
        mock_commit.assert_called_once()
        call_kwargs = mock_commit.call_args
        # third positional arg is the file list
        file_list = call_kwargs[0][2]
        assert "requirements.txt" in file_list
        assert "odoo_version.txt" in file_list
        # fourth positional arg is the message key
        assert call_kwargs[0][3] == "project_bootstrap"

    def test_odoo_version_file_included_even_if_not_synced(self, tmp_path):
        cfg = _make_config(files=["requirements.txt"])
        image = _make_image()
        runner = CliRunner()
        with patch("oops.commands.project.convert.config", cfg), patch(
            "oops.commands.project.convert.require_repository",
            return_value=(_make_local_repo(tmp_path), tmp_path),
        ), patch("oops.commands.project.convert.fetch_project_files"), patch(
            "oops.commands.project.convert.copy_project_files",
            return_value=["requirements.txt"],
        ), patch(
            "oops.commands.project.convert.find_available_images",
            return_value=[image],
        ), patch(
            "oops.commands.project.convert.prompt_select",
            return_value=f"{image.image}   {image.release.isoformat()}  Δ0d",
        ), patch(
            "oops.commands.project.convert.write_text_file"
        ), patch(
            "oops.commands.project.convert.commit"
        ) as mock_commit:
            runner.invoke(main, ["-v", "19"])

        file_list = mock_commit.call_args[0][2]
        assert "odoo_version.txt" in file_list
