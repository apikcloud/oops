# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_project_pipeline.py — tests/test_project_pipeline.py

"""Tests for oops/services/project_pipeline.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from oops.services.loc import LocStats
from oops.services.project_pipeline import build_inventory


def _fake_addon(technical_name: str, path: str, rel_path: str = "", **kw) -> MagicMock:
    addon = MagicMock()
    addon.technical_name = technical_name
    addon.path = path
    addon.rel_path = rel_path
    addon.symlinked = kw.get("symlinked", False)
    addon.symlink = kw.get("symlink", False)
    addon.location = kw.get("location", "local")
    addon.submodule = kw.get("submodule", "")
    addon.branch = kw.get("branch", "")
    addon.pull_request = kw.get("pull_request", False)
    addon.version = kw.get("version", "17.0.1.0.0")
    addon.classification = kw.get("classification", "custom")
    addon.author = kw.get("author", "Apik")
    return addon


class TestBuildInventory:
    def test_joins_git_state_and_loc(self, tmp_path: Path) -> None:
        addon = _fake_addon("my_module", str(tmp_path / "my_module"), classification="custom")
        with patch("oops.services.project_pipeline.list_submodules", return_value={}), \
                patch("oops.services.project_pipeline.find_addons", return_value=[addon]), \
                patch("oops.services.project_pipeline.enrich_addon"), \
                patch("oops.services.project_pipeline.get_addon_loc_cached",
                      return_value=LocStats(python=100, xml=20, javascript=0, docs=5)):
            inventory = build_inventory(MagicMock(), tmp_path, show_all=False, names=())

        assert "my_module" in inventory
        row = inventory["my_module"]
        assert row["classification"] == "custom"
        assert row["loc"]["total"] == 125
        assert row["path"] == str(tmp_path / "my_module")

    def test_name_filter_excludes_unmatched(self, tmp_path: Path) -> None:
        a = _fake_addon("a", str(tmp_path / "a"), rel_path=".third-party/repo_a")
        b = _fake_addon("b", str(tmp_path / "b"), rel_path=".third-party/repo_b")
        subs = {
            ".third-party/repo_a": {"name": "OCA/repo_a"},
            ".third-party/repo_b": {"name": "OCA/repo_b"},
        }
        with patch("oops.services.project_pipeline.list_submodules", return_value=subs), \
                patch("oops.services.project_pipeline.find_addons", return_value=[a, b]), \
                patch("oops.services.project_pipeline.enrich_addon"), \
                patch("oops.services.project_pipeline.get_addon_loc_cached", return_value=LocStats()):
            inventory = build_inventory(MagicMock(), tmp_path, show_all=False, names=("OCA/repo_a",))

        assert set(inventory) == {"a"}
