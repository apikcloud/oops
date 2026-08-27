# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_build_global.py — tests/test_build_global.py

"""Tests for oops/commands/misc/build_global.py — tier-origin mapping."""

from __future__ import annotations

from pathlib import Path

from oops.commands.misc.build_global import _ORIGIN_MAP, _TIER_ORIGIN_MAP


class TestTierOriginMap:
    def test_community_maps_to_odoo(self) -> None:
        assert _ORIGIN_MAP["community"] == "odoo"

    def test_odoo_addons_tier_maps_to_odoo_core(self) -> None:
        assert _TIER_ORIGIN_MAP[("odoo", "odoo/addons")] == "odoo_core"

    def test_flat_addons_tier_falls_back_to_base_name(self) -> None:
        base = _ORIGIN_MAP.get("community", "community")  # "odoo"
        assert _TIER_ORIGIN_MAP.get((base, "addons"), base) == "odoo"

    def test_enterprise_single_tier_falls_back_to_enterprise(self) -> None:
        assert _TIER_ORIGIN_MAP.get(("enterprise", "."), "enterprise") == "enterprise"


class TestWriteGlobalKbTierSources:
    def test_two_tier_sources_stored_as_tier_roots(self, tmp_path: Path) -> None:
        """write_kb + get_sources() roundtrip preserves per-tier roots."""
        from oops_engine.store import KBReader, write_kb

        addons_root = tmp_path / "community" / "addons"
        odoo_addons_root = tmp_path / "community" / "odoo" / "addons"
        addons_root.mkdir(parents=True)
        odoo_addons_root.mkdir(parents=True)

        sources = {
            "odoo": str(addons_root),
            "odoo_core": str(odoo_addons_root),
        }

        db_path = tmp_path / "test.db"
        write_kb(
            db_path=db_path,
            repo_id="odoo-core-17.0",
            odoo_version="17.0",
            sources=sources,
            scan_results=[],
        )

        with KBReader(db_path, repo_ids=["odoo-core-17.0"]) as kb:
            stored = kb.get_sources()

        assert stored["odoo"] == str(addons_root)
        assert stored["odoo_core"] == str(odoo_addons_root)
        assert stored.get("odoo") != str(tmp_path / "community")  # NOT the checkout root
