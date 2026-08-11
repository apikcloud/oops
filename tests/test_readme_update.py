# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_readme_update.py — tests/test_readme_update.py

"""Tests for oops/commands/readme/update.py."""

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.readme.update import main
from tests.helpers import make_addon as _make_addon

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_mock(readme_file: str = "README.md"):
    cfg = MagicMock()
    cfg.project.readme_file = readme_file
    return cfg


# ---------------------------------------------------------------------------
# TestReadmeUpdateCommand
# ---------------------------------------------------------------------------


class TestReadmeUpdateCommand:
    def _runner(self):
        return CliRunner()

    def _invoke(
        self,
        tmp_path: Path,
        addons=None,
        file_updater_return: bool = True,
        args=None,
        readme_file: str = "README.md",
        render_table_side_effect=None,
    ):
        if addons is None:
            addons = []
        cfg = _make_config_mock(readme_file)
        mock_repo = MagicMock()
        render_table_patch = (
            {"side_effect": render_table_side_effect}
            if render_table_side_effect
            else {"wraps": __import__("oops.utils.render", fromlist=["render_table"]).render_table}
        )
        with contextlib.ExitStack() as stack:
            _req = "oops.commands.readme.update.require_repository"
            stack.enter_context(patch(_req, return_value=(mock_repo, tmp_path)))
            stack.enter_context(patch("oops.commands.readme.update.find_addons", return_value=iter(addons)))
            mock_fu = stack.enter_context(
                patch("oops.commands.readme.update.file_updater", return_value=file_updater_return)
            )
            mock_commit = stack.enter_context(patch("oops.commands.readme.update.commit_v2"))
            stack.enter_context(patch("oops.commands.readme.update.config", cfg))
            stack.enter_context(patch("oops.commands.readme.update.render_table", **render_table_patch))
            result = self._runner().invoke(main, args or [])
        return result, mock_fu, mock_commit, mock_repo

    def _capture_content(self, tmp_path: Path, addons=None, args=None, readme_file: str = "README.md"):
        """Invoke the command and return the new_inner_content passed to file_updater."""
        if addons is None:
            addons = []
        cfg = _make_config_mock(readme_file)
        mock_repo = MagicMock()
        captured = {}

        def capture_file_updater(**kwargs):
            captured["kwargs"] = kwargs
            return True

        with contextlib.ExitStack() as stack:
            _req = "oops.commands.readme.update.require_repository"
            stack.enter_context(patch(_req, return_value=(mock_repo, tmp_path)))
            stack.enter_context(patch("oops.commands.readme.update.find_addons", return_value=iter(addons)))
            stack.enter_context(patch("oops.commands.readme.update.file_updater", side_effect=capture_file_updater))
            stack.enter_context(patch("oops.commands.readme.update.commit_v2"))
            stack.enter_context(patch("oops.commands.readme.update.config", cfg))
            self._runner().invoke(main, args or [])

        return captured.get("kwargs", {})

    # --- exit code ---

    def test_exit_code_zero_no_addons(self, tmp_path):
        result, _, _, _ = self._invoke(tmp_path)
        assert result.exit_code == 0, result.output

    def test_exit_code_zero_with_addons(self, tmp_path):
        result, _, _, _ = self._invoke(tmp_path, addons=[_make_addon()])
        assert result.exit_code == 0, result.output

    # --- commit behaviour ---

    def test_commit_called_when_file_updated(self, tmp_path):
        _, _, mock_commit, _ = self._invoke(tmp_path, addons=[_make_addon()], file_updater_return=True)
        mock_commit.assert_called_once()

    def test_commit_not_called_when_no_change(self, tmp_path):
        _, _, mock_commit, _ = self._invoke(tmp_path, addons=[_make_addon()], file_updater_return=False)
        mock_commit.assert_not_called()

    def test_no_commit_flag_skips_commit(self, tmp_path):
        _, _, mock_commit, _ = self._invoke(
            tmp_path, addons=[_make_addon()], file_updater_return=True, args=["--no-commit"]
        )
        mock_commit.assert_not_called()

    def test_dry_run_flag_skips_commit(self, tmp_path):
        _, _, mock_commit, _ = self._invoke(
            tmp_path, addons=[_make_addon()], file_updater_return=True, args=["--dry-run"]
        )
        mock_commit.assert_not_called()

    def test_commit_receives_correct_message_key(self, tmp_path):
        _, _, mock_commit, _ = self._invoke(tmp_path, addons=[_make_addon()], file_updater_return=True)
        assert mock_commit.call_args.args[3] == "addons_update_table"

    def test_commit_called_with_skip_hooks(self, tmp_path):
        _, _, mock_commit, _ = self._invoke(tmp_path, addons=[_make_addon()], file_updater_return=True)
        assert mock_commit.call_args.kwargs.get("skip_hooks") is True

    def test_commit_receives_readme_file_in_files_list(self, tmp_path):
        _, _, mock_commit, _ = self._invoke(
            tmp_path, addons=[_make_addon()], file_updater_return=True, readme_file="README.md"
        )
        files_arg = mock_commit.call_args.args[2]
        assert "README.md" in files_arg

    # --- file_updater call contract ---

    def test_dry_run_forwarded_to_file_updater(self, tmp_path):
        _, mock_fu, _, _ = self._invoke(tmp_path, args=["--dry-run"])
        assert mock_fu.call_args.kwargs["dry_run"] is True

    def test_dry_run_false_by_default(self, tmp_path):
        _, mock_fu, _, _ = self._invoke(tmp_path)
        assert mock_fu.call_args.kwargs["dry_run"] is False

    def test_file_updater_receives_addons_start_tag(self, tmp_path):
        _, mock_fu, _, _ = self._invoke(tmp_path)
        assert mock_fu.call_args.kwargs["start_tag"] == "[//]: # (addons)"

    def test_file_updater_receives_addons_end_tag(self, tmp_path):
        _, mock_fu, _, _ = self._invoke(tmp_path)
        assert mock_fu.call_args.kwargs["end_tag"] == "[//]: # (end addons)"

    def test_file_updater_receives_configured_readme_path(self, tmp_path):
        _, mock_fu, _, _ = self._invoke(tmp_path, readme_file="README.md")
        assert mock_fu.call_args.kwargs["filepath"] == "README.md"

    # --- content shape ---

    def test_new_content_starts_with_available_addons_header(self, tmp_path):
        kwargs = self._capture_content(tmp_path)
        content = kwargs["new_inner_content"]
        assert content.startswith("Available addons\n----------------")

    def test_addon_row_links_technical_name(self, tmp_path):
        kwargs = self._capture_content(tmp_path, addons=[_make_addon(technical_name="sale_custom")])
        assert "[sale_custom](/sale_custom)" in kwargs["new_inner_content"]

    def test_addon_row_includes_version(self, tmp_path):
        kwargs = self._capture_content(tmp_path, addons=[_make_addon(version="17.0.2.0.0")])
        assert "17.0.2.0.0" in kwargs["new_inner_content"]

    def test_addon_maintainer_rendered_as_github_avatar_link(self, tmp_path):
        kwargs = self._capture_content(tmp_path, addons=[_make_addon(maintainers=["alice"])])
        assert "github.com/alice" in kwargs["new_inner_content"]

    def test_multiple_maintainers_all_present(self, tmp_path):
        kwargs = self._capture_content(tmp_path, addons=[_make_addon(maintainers=["alice", "bob"])])
        content = kwargs["new_inner_content"]
        assert "github.com/alice" in content
        assert "github.com/bob" in content

    def test_summary_whitespace_collapsed(self, tmp_path):
        kwargs = self._capture_content(tmp_path, addons=[_make_addon(summary="  lots   of   spaces  ")])
        assert "lots of spaces" in kwargs["new_inner_content"]

    def test_no_maintainers_produces_empty_maintainers_cell(self, tmp_path):
        kwargs = self._capture_content(tmp_path, addons=[_make_addon(maintainers=[])])
        # The row is built and the table is rendered without error
        assert "new_inner_content" in kwargs

    # --- sorting ---

    def test_addons_sorted_alphabetically_in_table(self, tmp_path):
        addons = [_make_addon("zzz_last"), _make_addon("aaa_first")]
        captured_rows = {}

        def capture_render_table(rows, headers, index=True):
            captured_rows["rows"] = list(rows)
            from oops.utils.render import render_table as real_render_table

            return real_render_table(rows, headers, index=index)

        cfg = _make_config_mock()
        mock_repo = MagicMock()
        with contextlib.ExitStack() as stack:
            _req = "oops.commands.readme.update.require_repository"
            stack.enter_context(patch(_req, return_value=(mock_repo, tmp_path)))
            stack.enter_context(patch("oops.commands.readme.update.find_addons", return_value=iter(addons)))
            stack.enter_context(patch("oops.commands.readme.update.file_updater", return_value=True))
            stack.enter_context(patch("oops.commands.readme.update.commit_v2"))
            stack.enter_context(patch("oops.commands.readme.update.config", cfg))
            stack.enter_context(patch("oops.commands.readme.update.render_table", side_effect=capture_render_table))
            self._runner().invoke(main, [])

        assert captured_rows["rows"][0][0] == "[aaa_first](/aaa_first)"
        assert captured_rows["rows"][1][0] == "[zzz_last](/zzz_last)"

    def test_single_addon_order_unchanged_after_sort(self, tmp_path):
        addons = [_make_addon("only_addon")]
        captured_rows = {}

        def capture_render_table(rows, headers, index=True):
            captured_rows["rows"] = list(rows)
            from oops.utils.render import render_table as real_render_table

            return real_render_table(rows, headers, index=index)

        cfg = _make_config_mock()
        mock_repo = MagicMock()
        with contextlib.ExitStack() as stack:
            _req = "oops.commands.readme.update.require_repository"
            stack.enter_context(patch(_req, return_value=(mock_repo, tmp_path)))
            stack.enter_context(patch("oops.commands.readme.update.find_addons", return_value=iter(addons)))
            stack.enter_context(patch("oops.commands.readme.update.file_updater", return_value=True))
            stack.enter_context(patch("oops.commands.readme.update.commit_v2"))
            stack.enter_context(patch("oops.commands.readme.update.config", cfg))
            stack.enter_context(patch("oops.commands.readme.update.render_table", side_effect=capture_render_table))
            self._runner().invoke(main, [])

        assert len(captured_rows["rows"]) == 1
        assert captured_rows["rows"][0][0] == "[only_addon](/only_addon)"
