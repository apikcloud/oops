# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_oops_engine_addons.py — tests/test_oops_engine_addons.py

"""Tests for oops_engine/addons.py."""

from pathlib import Path

from oops_engine.addons import discover_addons, find_addon_dirs, find_addons, find_modified_addons


def _make_terp_addon(base: Path, name: str) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "__terp__.py").write_text('{"name": "Terp Addon"}')
    return d


def _make_addon(base: Path, rel_dir: str, name: str, author: str = "Acme") -> Path:
    d = base / rel_dir / name if rel_dir else base / name
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"name": name, "author": author, "depends": []}
    (d / "__manifest__.py").write_text(repr(manifest))
    return d


class TestFindModifiedAddonsTerp:
    def test_recognizes_terp_only_addon(self, tmp_path):
        addon_dir = _make_terp_addon(tmp_path, "legacy_addon")
        result = find_modified_addons([str(addon_dir / "models" / "res_partner.py")])
        assert result == ["legacy_addon"]


class TestFindAddonDirsTerp:
    def test_recognizes_terp_only_addon(self, tmp_path):
        addon_dir = _make_terp_addon(tmp_path, "legacy_addon")
        result = find_addon_dirs(tmp_path)
        assert addon_dir in result


class TestFindAddonsTerp:
    def test_recognizes_terp_only_addon(self, tmp_path):
        _make_terp_addon(tmp_path, "legacy_addon")
        result = list(find_addons(tmp_path))
        assert [a.technical_name for a in result] == ["legacy_addon"]


class TestDiscoverAddons:
    def test_sorts_by_technical_name(self, tmp_path):
        _make_addon(tmp_path, "", "zebra_mod")
        _make_addon(tmp_path, "", "alpha_mod")

        addons = discover_addons(tmp_path, {})

        assert [a.technical_name for a in addons] == ["alpha_mod", "zebra_mod"]

    def test_enriches_classification_from_subs(self, tmp_path):
        _make_addon(tmp_path, "sub_a", "oca_mod", author="Some Vendor")
        subs = {"sub_a": {"name": "OCA/somerepo", "branch": "18.0"}}

        addons = discover_addons(tmp_path, subs)

        addon = addons[0]
        assert addon.submodule == "OCA/somerepo"
        assert addon.branch == "18.0"
        assert addon.classification == "oca"

    def test_rel_paths_filter_restricts_result(self, tmp_path):
        _make_addon(tmp_path, "sub_a", "addon_a")
        _make_addon(tmp_path, "sub_b", "addon_b")

        addons = discover_addons(tmp_path, {}, rel_paths={"sub_a"})

        assert [a.technical_name for a in addons] == ["addon_a"]

    def test_shallow_flag_forwarded(self, tmp_path):
        _make_addon(tmp_path, "level1/level2", "addon_deep")

        shallow_addons = discover_addons(tmp_path, {}, shallow=True)
        deep_addons = discover_addons(tmp_path, {}, shallow=False)

        assert [a.technical_name for a in shallow_addons] == []
        assert [a.technical_name for a in deep_addons] == ["addon_deep"]
