"""Tests for oops.commands.project.convert."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.project.convert import _build_plan, main
from oops.core.models import ImageInfo, Result


def _make_config(
    remote_url: "str | None" = "https://example.com/repo.git",
    branch: "str | None" = "main",
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


def _image_choice(image):
    return f"{image.image}   {image.release.isoformat()}  Δ0d"


# ---------------------------------------------------------------------------
# _build_plan unit tests
# ---------------------------------------------------------------------------


class TestBuildPlan:
    def test_copy_actions_for_existing_files(self):
        image = _make_image()
        plan = _build_plan(
            files={"requirements.txt", "packages.txt", "odoo_version.txt"},
            existing_files={"requirements.txt", "packages.txt"},
            image=image,
            version="19.0",
            file_odoo_version="odoo_version.txt",
        )
        kinds = {a.label: a.kind for a in plan.actionable}
        assert kinds["requirements.txt"] == "copy"
        assert kinds["packages.txt"] == "copy"
        assert kinds["odoo_version.txt"] == "write"

    def test_missing_files_excluded_from_plan(self):
        image = _make_image()
        plan = _build_plan(
            files={"requirements.txt", "packages.txt", "odoo_version.txt"},
            existing_files={"requirements.txt"},  # packages.txt absent from source
            image=image,
            version="19.0",
            file_odoo_version="odoo_version.txt",
        )
        labels = {a.label for a in plan.actionable}
        assert "packages.txt" not in labels

    def test_version_file_always_write_action(self):
        image = _make_image()
        plan = _build_plan(
            files={"odoo_version.txt"},
            existing_files=set(),  # nothing from source
            image=image,
            version="19.0",
            file_odoo_version="odoo_version.txt",
        )
        assert len(plan.actionable) == 1
        assert plan.actionable[0].kind == "write"
        assert plan.actionable[0].data["image"] == image.image

    def test_write_action_stores_image(self):
        image = _make_image(tag="apik/odoo:19.0-20250701-enterprise")
        plan = _build_plan(
            files={"odoo_version.txt"},
            existing_files=set(),
            image=image,
            version="19.0",
            file_odoo_version="odoo_version.txt",
        )
        write_action = next(a for a in plan.actionable if a.kind == "write")
        assert write_action.data["image"] == "apik/odoo:19.0-20250701-enterprise"


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
    def _invoke(self, tmp_path, cfg, image, synced_files=("requirements.txt",), extra_args=()):
        """Run convert with all external I/O mocked.

        fetch_project_files side_effect creates synced_files in the real tmpdir
        so that _build_plan sees the correct existing_files set.
        run_mutation_workflow and render_and_raise are mocked to avoid terminal
        rendering in tests.
        """
        def fake_fetch(_url, _branch, _files, tmpdir):
            for f in synced_files:
                (tmpdir / f).write_text("")

        mock_commit = MagicMock(return_value=Result())
        runner = CliRunner()
        with patch("oops.commands.project.convert.config", cfg), \
             patch("oops.commands.project.convert.require_repository",
                   return_value=(_make_local_repo(tmp_path), tmp_path)), \
             patch("oops.commands.project.convert.find_available_images", return_value=[image]), \
             patch("oops.commands.project.convert.fetch_project_files", side_effect=fake_fetch), \
             patch("oops.commands.project.convert.prompt_select", return_value=_image_choice(image)), \
             patch("oops.commands.project.convert.run_mutation_workflow", return_value=Result()), \
             patch("oops.commands.project.convert.render_and_raise"), \
             patch("oops.commands.project.convert.commit_v2", mock_commit):
            result = runner.invoke(main, ["-v", "19", *extra_args])
        return result, mock_commit

    def test_creates_bootstrap_commit(self, tmp_path):
        cfg = _make_config(
            files=["requirements.txt"],
            mandatory_files={"requirements.txt", "odoo_version.txt"},
        )
        image = _make_image()
        result, mock_commit = self._invoke(tmp_path, cfg, image, synced_files=["requirements.txt"])

        assert result.exit_code == 0
        mock_commit.assert_called_once()
        file_list = mock_commit.call_args[0][2]
        assert "requirements.txt" in file_list
        assert "odoo_version.txt" in file_list
        assert mock_commit.call_args[0][3] == "project_bootstrap"

    def test_odoo_version_file_included_even_if_not_synced(self, tmp_path):
        """Version file always in commit list even when absent from sync source."""
        cfg = _make_config(files=["requirements.txt"])
        image = _make_image()
        _, mock_commit = self._invoke(tmp_path, cfg, image, synced_files=["requirements.txt"])

        file_list = mock_commit.call_args[0][2]
        assert "odoo_version.txt" in file_list

    def test_no_commit_skips_commit(self, tmp_path):
        cfg = _make_config(files=["requirements.txt"])
        image = _make_image()
        result, mock_commit = self._invoke(
            tmp_path, cfg, image, synced_files=["requirements.txt"], extra_args=["--no-commit"]
        )

        assert result.exit_code == 0
        mock_commit.assert_not_called()
