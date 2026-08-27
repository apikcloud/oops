# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_oops_engine_addons.py — tests/test_oops_engine_addons.py

"""Tests for oops_engine/addons.py."""

from pathlib import Path

from oops_engine.addons import find_addon_dirs, find_addons, find_modified_addons


def _make_terp_addon(base: Path, name: str) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "__terp__.py").write_text('{"name": "Terp Addon"}')
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
