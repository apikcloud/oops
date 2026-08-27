# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_addons_wrappers.py — tests/oops_engine/test_addons_wrappers.py

"""Tests for the find+dedup+enrich wrapper helpers in oops_engine.addons."""

from pathlib import Path

from oops_engine.addons import dedup_addons_by_path, enrich_addon_from_subs
from oops_engine.models import Addon


def _make_addon(path: str, rel_path: str = "", symlinked: bool = False) -> Addon:
    return Addon(
        path=path,
        rel_path=rel_path,
        technical_name=Path(path).name,
        symlink=symlinked,
        root=True,
        version="",
        author="",
        maintainers=[],
        summary="",
        external_dependencies={},
        depends=[],
        installable=True,
    )


class TestDedupAddonsByPath:
    def test_prefers_symlinked_entry_on_collision(self, tmp_path, monkeypatch):
        real = _make_addon(str(tmp_path / "a"), symlinked=False)
        symlinked = _make_addon(str(tmp_path / "a"), symlinked=True)

        import oops_engine.addons as addons_mod

        monkeypatch.setattr(addons_mod, "find_addons", lambda root, shallow=False: iter([real, symlinked]))

        seen = dedup_addons_by_path(tmp_path)
        assert seen[str(tmp_path / "a")] is symlinked

    def test_no_collision_keeps_both(self, tmp_path, monkeypatch):
        a = _make_addon(str(tmp_path / "a"))
        b = _make_addon(str(tmp_path / "b"))

        import oops_engine.addons as addons_mod

        monkeypatch.setattr(addons_mod, "find_addons", lambda root, shallow=False: iter([a, b]))

        seen = dedup_addons_by_path(tmp_path)
        assert set(seen) == {str(tmp_path / "a"), str(tmp_path / "b")}


class TestEnrichAddonFromSubs:
    def test_looks_up_sub_by_rel_path_and_enriches(self):
        addon = _make_addon("/repo/oca/sale_x", rel_path=".third-party/sale_repo")
        subs = {".third-party/sale_repo": {"name": "OCA/sale_repo", "branch": "17.0", "pr": False}}

        enrich_addon_from_subs(addon, subs, author="Apik", prefix="apik_", owner="apikcloud")

        assert addon.submodule == "OCA/sale_repo"
        assert addon.branch == "17.0"
        assert addon.classification == "oca"

    def test_missing_rel_path_enriches_with_empty_sub(self):
        addon = _make_addon("/repo/local_addon", rel_path="")

        enrich_addon_from_subs(addon, {}, author="Apik", prefix="apik_", owner="apikcloud")

        assert addon.submodule == ""
        assert addon.pull_request is False
