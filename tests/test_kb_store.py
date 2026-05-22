# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_kb_store.py — tests/test_kb_store.py

"""Tests for oops/kb/store.py schema, write path, and KBReader extensions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from oops.kb.store import KBReader, write_project_kb

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(
    db_path: Path,
    symbols: list[dict] | None = None,
    field_refs: list[dict] | None = None,
    modules: dict | None = None,
    views: list[dict] | None = None,
    actions: list[dict] | None = None,
    menus: list[dict] | None = None,
) -> None:
    scan_results = [
        {
            "modules": modules or {},
            "symbols": symbols or [],
            "field_refs": field_refs or [],
            "views": views or [],
            "actions": actions or [],
            "menus": menus or [],
        }
    ]
    write_project_kb(
        db_path=db_path,
        odoo_version="17.0",
        project="test",
        scope=[],
        sources={"odoo": "/odoo"},
        scan_results=scan_results,
    )


def _sym(model: str, name: str, kind: str, **kw: object) -> dict:
    return {
        "model": model,
        "name": name,
        "kind": kind,
        "origin": "odoo",
        "module": kw.get("module", "sale"),
        "source_file": "addons/sale/models/sale.py",
        "source_line": 10,
        "field_type": kw.get("field_type"),
        "section": kw.get("section"),
    }


# ---------------------------------------------------------------------------
# TestDDL — schema shape
# ---------------------------------------------------------------------------


class TestDDL:
    def test_symbols_has_field_type_column(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        cols = {row[1] for row in con.execute("PRAGMA table_info(symbols)").fetchall()}
        assert "field_type" in cols
        assert "section" in cols
        con.close()

    def test_field_refs_table_exists(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "field_refs" in tables
        con.close()

    def test_schema_version_in_meta(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        with KBReader(db_path) as kb:
            meta = kb.get_meta()
        assert meta.get("schema_version") == "4"

    def test_write_twice_applies_schema_cleanly(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "write", "method", section="CRUD METHODS")])
        _write(db_path, symbols=[_sym("sale.order", "name", "field", field_type="Char")])
        with KBReader(db_path) as kb:
            # Second write replaced the first; only the new symbol should be there.
            syms = kb.get_model_symbols("sale.order")
        assert len(syms) == 1
        assert syms[0]["name"] == "name"


# ---------------------------------------------------------------------------
# TestRoundTrip — write then read back
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_field_type_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "active", "field", field_type="Boolean")])
        with KBReader(db_path) as kb:
            entries = kb.get_symbol("sale.order", "active", "field")
        assert len(entries) == 1
        assert entries[0]["field_type"] == "Boolean"

    def test_section_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "action_confirm", "method", section="ACTION METHODS")])
        with KBReader(db_path) as kb:
            entries = kb.get_symbol("sale.order", "action_confirm", "method")
        assert entries[0]["section"] == "ACTION METHODS"

    def test_field_refs_round_trip(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            field_refs=[
                {
                    "model": "sale.order",
                    "field_name": "amount_total",
                    "module": "sale",
                    "kwarg": "compute",
                    "target_method": "_compute_amount_total",
                }
            ],
        )
        with KBReader(db_path) as kb:
            refs = kb.get_field_refs_for_method("sale.order", "_compute_amount_total")
        assert len(refs) == 1
        assert refs[0]["kwarg"] == "compute"
        assert refs[0]["field_name"] == "amount_total"

    def test_get_field_refs_for_field(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            field_refs=[
                {
                    "model": "sale.order",
                    "field_name": "amount_total",
                    "module": "sale",
                    "kwarg": "compute",
                    "target_method": "_compute_amount",
                }
            ],
        )
        with KBReader(db_path) as kb:
            refs = kb.get_field_refs_for_field("sale.order", "amount_total")
        assert len(refs) == 1
        assert refs[0]["target_method"] == "_compute_amount"

    def test_null_field_type_for_methods(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "write", "method")])
        with KBReader(db_path) as kb:
            entries = kb.get_symbol("sale.order", "write", "method")
        assert entries[0]["field_type"] is None

    def test_null_section_for_fields(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "name", "field", field_type="Char")])
        with KBReader(db_path) as kb:
            entries = kb.get_symbol("sale.order", "name", "field")
        assert entries[0]["section"] is None


# ---------------------------------------------------------------------------
# TestStaleness — schema version check
# ---------------------------------------------------------------------------


class TestStaleness:
    def test_kb_without_schema_version_is_stale(self, tmp_path):
        """A v1 KB (no schema_version row) is flagged as stale."""
        from oops.kb.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        # Write a KB and then manually delete the schema_version row.
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        con.execute("DELETE FROM meta WHERE key='schema_version'")
        con.commit()
        con.close()

        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        assert stale is True
        assert "schema" in reason.lower()

    def test_kb_with_wrong_schema_version_is_stale(self, tmp_path):
        from oops.kb.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        _write(db_path)
        # Override the version to something old.
        con = sqlite3.connect(str(db_path))
        con.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
        con.commit()
        con.close()

        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        assert stale is True
        assert "schema" in reason.lower()

    def test_current_schema_version_is_fresh(self, tmp_path):
        from oops.kb.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        _write(db_path)

        # No global KB → only schema version check matters here.
        # Patch global KB path to a non-existent path so it doesn't block freshness.
        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        # KB is fresh from a schema perspective (global KB missing is OK — no timestamp
        # comparison possible, so it doesn't flag stale for that reason alone).
        # The important thing is "schema" is not in reason.
        assert "schema" not in reason


# ---------------------------------------------------------------------------
# TestWriteResult — verify Result returned by write_project_kb
# ---------------------------------------------------------------------------


class TestWriteResult:
    def test_result_data_has_expected_keys(self, tmp_path):
        db_path = tmp_path / "kb.db"
        result = write_project_kb(
            db_path=db_path,
            odoo_version="17.0",
            project="test",
            scope=[],
            sources={"odoo": "/odoo"},
            scan_results=[{"modules": {}, "symbols": [], "field_refs": [], "model_origins": []}],
        )
        assert result.ok
        assert result.data is not None
        for key in (
            "file", "modules", "symbols", "fields", "methods",
            "field_refs", "model_origins", "views", "actions", "menus",
        ):
            assert key in result.data, f"Missing key: {key}"

    def test_result_counters_match_inserted_data(self, tmp_path):
        db_path = tmp_path / "kb.db"
        sym = {
            "model": "sale.order", "name": "name", "kind": "field",
            "origin": "odoo", "module": "sale",
            "source_file": "sale/models/sale.py", "source_line": 10,
            "field_type": "Char", "section": None,
        }
        result = write_project_kb(
            db_path=db_path,
            odoo_version="17.0",
            project="test",
            scope=["sale"],
            sources={"odoo": "/odoo"},
            scan_results=[{
                "modules": {"sale": {"origin": "odoo", "depends": []}},
                "symbols": [sym],
                "field_refs": [],
                "model_origins": [],
            }],
        )
        assert result.data["modules"] == 1
        assert result.data["symbols"] == 1
        assert result.data["fields"] == 1

    def test_result_messages_empty_on_clean_write(self, tmp_path):
        db_path = tmp_path / "kb.db"
        result = write_project_kb(
            db_path=db_path,
            odoo_version="17.0",
            project="test",
            scope=[],
            sources={},
            scan_results=[],
        )
        assert result.warnings == []
        assert result.errors == []


# ---------------------------------------------------------------------------
# TestXmlTables — views / actions / menus ingestion
# ---------------------------------------------------------------------------


def _view(xml_id: str, module: str = "sale", **kw: object) -> dict:
    return {
        "xml_id": xml_id,
        "module": module,
        "origin": kw.get("origin", "odoo"),
        "name": kw.get("name"),
        "model": kw.get("model", "sale.order"),
        "view_type": kw.get("view_type", "form"),
        "inherit_id": kw.get("inherit_id"),
        "mode": kw.get("mode", "primary"),
        "source_file": kw.get("source_file", "sale/views/form.xml"),
        "source_line": kw.get("source_line", 1),
        "fields_json": kw.get("fields_json", "[]"),
        "buttons_json": kw.get("buttons_json", "[]"),
    }


def _action(xml_id: str, module: str = "sale", **kw: object) -> dict:
    return {
        "xml_id": xml_id,
        "module": module,
        "origin": kw.get("origin", "odoo"),
        "name": kw.get("name", "My Action"),
        "model": kw.get("model", "sale.order"),
        "view_id": kw.get("view_id"),
        "domain": kw.get("domain"),
        "source_file": kw.get("source_file", "sale/views/act.xml"),
        "source_line": kw.get("source_line", 1),
    }


def _menu(xml_id: str, module: str = "sale", **kw: object) -> dict:
    return {
        "xml_id": xml_id,
        "module": module,
        "origin": kw.get("origin", "odoo"),
        "name": kw.get("name", "My Menu"),
        "action": kw.get("action"),
        "parent_id": kw.get("parent_id"),
        "source_file": kw.get("source_file", "sale/views/menu.xml"),
        "source_line": kw.get("source_line", 1),
    }


class TestXmlTables:
    def test_tables_exist_after_empty_write(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        import sqlite3
        con = sqlite3.connect(str(db_path))
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        con.close()
        assert "views" in tables
        assert "actions" in tables
        assert "menus" in tables

    def test_view_ingestion_round_trip(self, tmp_path):
        db_path = tmp_path / "kb.db"
        v = _view("sale.view_order_form", fields_json='["name","partner_id"]')
        write_project_kb(
            db_path=db_path, odoo_version="17.0", project="test", scope=[],
            sources={}, scan_results=[{"views": [v], "actions": [], "menus": []}],
        )
        with KBReader(db_path) as kb:
            views = kb.get_views()
            single = kb.get_view("sale.view_order_form")
        assert len(views) == 1
        assert views[0]["xml_id"] == "sale.view_order_form"
        assert views[0]["view_type"] == "form"
        assert single is not None
        assert single["xml_id"] == "sale.view_order_form"

    def test_action_ingestion_round_trip(self, tmp_path):
        db_path = tmp_path / "kb.db"
        a = _action("sale.action_orders")
        write_project_kb(
            db_path=db_path, odoo_version="17.0", project="test", scope=[],
            sources={}, scan_results=[{"views": [], "actions": [a], "menus": []}],
        )
        with KBReader(db_path) as kb:
            actions = kb.get_actions()
        assert len(actions) == 1
        assert actions[0]["xml_id"] == "sale.action_orders"

    def test_menu_ingestion_round_trip(self, tmp_path):
        db_path = tmp_path / "kb.db"
        m = _menu("sale.menu_root")
        write_project_kb(
            db_path=db_path, odoo_version="17.0", project="test", scope=[],
            sources={}, scan_results=[{"views": [], "actions": [], "menus": [m]}],
        )
        with KBReader(db_path) as kb:
            menus = kb.get_menus()
        assert len(menus) == 1
        assert menus[0]["xml_id"] == "sale.menu_root"

    def test_second_write_clears_old_rows(self, tmp_path):
        db_path = tmp_path / "kb.db"
        write_project_kb(
            db_path=db_path, odoo_version="17.0", project="test", scope=[],
            sources={}, scan_results=[{"views": [_view("sale.view_a")], "actions": [], "menus": []}],
        )
        write_project_kb(
            db_path=db_path, odoo_version="17.0", project="test", scope=[],
            sources={}, scan_results=[{"views": [_view("sale.view_b")], "actions": [], "menus": []}],
        )
        with KBReader(db_path) as kb:
            views = kb.get_views()
        xml_ids = {v["xml_id"] for v in views}
        assert "sale.view_a" not in xml_ids
        assert "sale.view_b" in xml_ids

    def test_duplicate_xml_id_uses_last_write(self, tmp_path):
        db_path = tmp_path / "kb.db"
        v1 = _view("sale.view_form", view_type="form")
        v2 = _view("sale.view_form", view_type="list")
        write_project_kb(
            db_path=db_path, odoo_version="17.0", project="test", scope=[],
            sources={}, scan_results=[{"views": [v1, v2], "actions": [], "menus": []}],
        )
        with KBReader(db_path) as kb:
            views = kb.get_views()
        assert len(views) == 1
        assert views[0]["view_type"] == "list"

    def test_get_view_missing_returns_none(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        with KBReader(db_path) as kb:
            assert kb.get_view("nonexistent.view") is None

    def test_stats_include_xml_counts(self, tmp_path):
        db_path = tmp_path / "kb.db"
        result = write_project_kb(
            db_path=db_path, odoo_version="17.0", project="test", scope=[],
            sources={}, scan_results=[{
                "views": [_view("sale.view_form")],
                "actions": [_action("sale.action")],
                "menus": [_menu("sale.menu")],
            }],
        )
        assert result.data is not None
        assert result.data["views"] == 1
        assert result.data["actions"] == 1
        assert result.data["menus"] == 1


# ---------------------------------------------------------------------------
# TestModuleHelpers
# ---------------------------------------------------------------------------


class TestModuleHelpers:
    def test_get_module_views_filtered(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            views=[
                _view("mod_a.view_form_1", module="mod_a"),
                _view("mod_a.view_list_1", module="mod_a"),
                _view("mod_b.view_form_1", module="mod_b"),
            ],
        )
        with KBReader(db_path) as kb:
            rows = kb.get_module_views("mod_a")
        assert len(rows) == 2
        assert all(r["xml_id"].startswith("mod_a.") for r in rows)

    def test_get_module_action_count(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            actions=[
                _action("mod_a.act1", module="mod_a"),
                _action("mod_a.act2", module="mod_a"),
                _action("mod_b.act1", module="mod_b"),
            ],
        )
        with KBReader(db_path) as kb:
            assert kb.get_module_action_count("mod_a") == 2

    def test_get_module_menu_count(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            menus=[
                _menu("mod_a.menu1", module="mod_a"),
                _menu("mod_a.menu2", module="mod_a"),
                _menu("mod_b.menu1", module="mod_b"),
            ],
        )
        with KBReader(db_path) as kb:
            assert kb.get_module_menu_count("mod_a") == 2

    def test_get_module_views_empty(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        with KBReader(db_path) as kb:
            rows = kb.get_module_views("nonexistent_module")
        assert rows == []
