# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_oops_engine_store.py — tests/test_oops_engine_store.py

"""Tests for oops_engine/store.py schema, write path, and KBReader extensions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from oops_engine.identity import local_repo_id
from oops_engine.store import KBReader, write_kb

_REPO_ID = "test"

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
    model_origins: list[dict] | None = None,
    repo_id: str = _REPO_ID,
) -> None:
    scan_results = [
        {
            "modules": modules or {},
            "symbols": symbols or [],
            "field_refs": field_refs or [],
            "views": views or [],
            "actions": actions or [],
            "menus": menus or [],
            "model_origins": model_origins or [],
        }
    ]
    write_kb(
        db_path=db_path,
        repo_id=repo_id,
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
        "source_end_line": kw.get("source_end_line", 12),
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
        assert "source_end_line" in cols
        con.close()

    def test_views_has_source_end_line_column(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        cols = {row[1] for row in con.execute("PRAGMA table_info(views)").fetchall()}
        assert "source_end_line" in cols
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
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            meta = kb.get_meta()
        assert meta.get("schema_version") == "10"

    def test_write_twice_applies_schema_cleanly(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "write", "method", section="CRUD METHODS")])
        _write(db_path, symbols=[_sym("sale.order", "name", "field", field_type="Char")])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            # Second write replaced the first; only the new symbol should be there.
            syms = kb.get_model_symbols("sale.order")
        assert len(syms) == 1
        assert syms[0]["name"] == "name"

    def test_repo_meta_table_exists_and_meta_does_not(self, tmp_path):
        """v10: the old unscoped 'meta' table is fully replaced by 'repo_meta'."""
        db_path = tmp_path / "kb.db"
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        con.close()
        assert "repo_meta" in tables
        assert "meta" not in tables


# ---------------------------------------------------------------------------
# TestRepoScoping — repo_id isolation (Phase 3)
# ---------------------------------------------------------------------------


class TestRepoScoping:
    def test_write_kb_scopes_by_repo_id(self, tmp_path):
        """Two repo_ids' rows coexist in the same file without colliding, and
        rewriting one repo_id never touches the other's rows."""
        db_path = tmp_path / "kb.db"
        _write(db_path, repo_id="a", modules={"module_a": {"origin": "custom", "depends": []}})
        _write(db_path, repo_id="b", modules={"module_b": {"origin": "custom", "depends": []}})

        with KBReader(db_path, repo_ids=["a"]) as kb:
            assert kb.get_modules() == {
                "module_a": {"origin": "custom", "depends": [], "application": False, "app": None}
            }
        with KBReader(db_path, repo_ids=["b"]) as kb:
            assert kb.get_modules() == {
                "module_b": {"origin": "custom", "depends": [], "application": False, "app": None}
            }
        with KBReader(db_path, repo_ids=["a", "b"]) as kb:
            assert set(kb.get_modules()) == {"module_a", "module_b"}

        # Re-writing "a" with an empty scan must not touch "b"'s rows.
        _write(db_path, repo_id="a", modules={})
        with KBReader(db_path, repo_ids=["a"]) as kb:
            assert kb.get_modules() == {}
        with KBReader(db_path, repo_ids=["b"]) as kb:
            assert "module_b" in kb.get_modules()

    def test_get_meta_defaults_to_first_repo_id(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, repo_id="a")
        _write(db_path, repo_id="b")
        with KBReader(db_path, repo_ids=["a", "b"]) as kb:
            # get_meta() with no arg reads the first repo_id given at construction.
            assert kb.get_meta()["schema_version"] == "10"
            assert kb.get_meta(repo_id="b")["schema_version"] == "10"

    def test_kbreader_requires_at_least_one_repo_id(self, tmp_path):
        import pytest

        db_path = tmp_path / "kb.db"
        _write(db_path)
        with pytest.raises(ValueError):
            KBReader(db_path, repo_ids=[])


# ---------------------------------------------------------------------------
# TestRoundTrip — write then read back
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_field_type_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "active", "field", field_type="Boolean")])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            entries = kb.get_symbol("sale.order", "active", "field")
        assert len(entries) == 1
        assert entries[0]["field_type"] == "Boolean"

    def test_section_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "action_confirm", "method", section="ACTION METHODS")])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
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
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
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
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            refs = kb.get_field_refs_for_field("sale.order", "amount_total")
        assert len(refs) == 1
        assert refs[0]["target_method"] == "_compute_amount"

    def test_null_field_type_for_methods(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "write", "method")])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            entries = kb.get_symbol("sale.order", "write", "method")
        assert entries[0]["field_type"] is None

    def test_null_section_for_fields(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path, symbols=[_sym("sale.order", "name", "field", field_type="Char")])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            entries = kb.get_symbol("sale.order", "name", "field")
        assert entries[0]["section"] is None

    def test_symbol_source_end_line_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            symbols=[_sym("sale.order", "action_confirm", "method", section="ACTION METHODS", source_end_line=42)],
        )
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            entries = kb.get_symbol("sale.order", "action_confirm", "method")
        assert entries[0]["source_end_line"] == 42
        assert entries[0]["source_end_line"] >= entries[0]["source_line"]

    def test_model_origins_description_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            model_origins=[
                {
                    "model": "res.partner",
                    "module": "base",
                    "origin": "odoo",
                    "role": "create",
                    "model_type": "model",
                    "inherit_json": "[]",
                    "inherits_json": "{}",
                    "source_file": "addons/base/models/res_partner.py",
                    "source_line": 10,
                    "description": "Contact",
                }
            ],
        )
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            creators = kb.get_model_creators("res.partner")
            assert creators[0]["description"] == "Contact"
            assert kb.get_model_description("res.partner") == "Contact"

    def test_model_description_none_when_absent(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            model_origins=[
                {
                    "model": "x.thing",
                    "module": "mymod",
                    "origin": "custom",
                    "role": "create",
                    "model_type": "model",
                    "inherit_json": "[]",
                    "inherits_json": "{}",
                    "source_file": "models/thing.py",
                    "source_line": 5,
                    "description": None,
                }
            ],
        )
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            assert kb.get_model_description("x.thing") is None
            assert kb.get_model_creators("x.thing")[0]["description"] is None


# ---------------------------------------------------------------------------
# TestStaleness — schema version check
# ---------------------------------------------------------------------------


class TestStaleness:
    def test_kb_without_schema_version_is_stale(self, tmp_path):
        """A KB with no schema_version row for the project's own repo_id is flagged as stale."""
        from oops_engine.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        repo_id = local_repo_id(tmp_path)
        # Write a KB (under the repo_id is_project_kb_stale will actually look up)
        # and then manually delete the schema_version row.
        _write(db_path, repo_id=repo_id)
        con = sqlite3.connect(str(db_path))
        con.execute("DELETE FROM repo_meta WHERE key='schema_version' AND repo_id=?", (repo_id,))
        con.commit()
        con.close()

        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        assert stale is True
        assert "schema" in reason.lower()

    def test_kb_with_wrong_schema_version_is_stale(self, tmp_path):
        from oops_engine.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        repo_id = local_repo_id(tmp_path)
        _write(db_path, repo_id=repo_id)
        # Override the version to something old.
        con = sqlite3.connect(str(db_path))
        con.execute("UPDATE repo_meta SET value='1' WHERE key='schema_version' AND repo_id=?", (repo_id,))
        con.commit()
        con.close()

        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        assert stale is True
        assert "schema" in reason.lower()

    def test_current_schema_version_is_fresh(self, tmp_path):
        from oops_engine.build import is_project_kb_stale

        cache = tmp_path / ".oops-cache"
        cache.mkdir()
        db_path = cache / "kb.db"
        _write(db_path, repo_id=local_repo_id(tmp_path))

        # No global KB → only schema version check matters here.
        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        # KB is fresh from a schema perspective (global KB missing is OK — no timestamp
        # comparison possible, so it doesn't flag stale for that reason alone).
        # The important thing is "schema" is not in reason.
        assert "schema" not in reason


# ---------------------------------------------------------------------------
# TestWriteResult — verify Result returned by write_kb
# ---------------------------------------------------------------------------


class TestWriteResult:
    def test_result_data_has_expected_keys(self, tmp_path):
        db_path = tmp_path / "kb.db"
        result = write_kb(
            db_path=db_path,
            repo_id=_REPO_ID,
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
        result = write_kb(
            db_path=db_path,
            repo_id=_REPO_ID,
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
        result = write_kb(
            db_path=db_path,
            repo_id=_REPO_ID,
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
        "source_end_line": kw.get("source_end_line", 5),
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


def _write_xml(db_path: Path, views=None, actions=None, menus=None) -> "object":
    return write_kb(
        db_path=db_path, repo_id=_REPO_ID, odoo_version="17.0", project="test", scope=[],
        sources={}, scan_results=[{"views": views or [], "actions": actions or [], "menus": menus or []}],
    )


class TestXmlTables:
    def test_tables_exist_after_empty_write(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        con = sqlite3.connect(str(db_path))
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        con.close()
        assert "views" in tables
        assert "actions" in tables
        assert "menus" in tables

    def test_view_ingestion_round_trip(self, tmp_path):
        db_path = tmp_path / "kb.db"
        v = _view("sale.view_order_form", fields_json='["name","partner_id"]')
        _write_xml(db_path, views=[v])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            views = kb.get_views()
            single = kb.get_view("sale.view_order_form")
        assert len(views) == 1
        assert views[0]["xml_id"] == "sale.view_order_form"
        assert views[0]["view_type"] == "form"
        assert single is not None
        assert single["xml_id"] == "sale.view_order_form"

    def test_view_source_end_line_round_trips(self, tmp_path):
        db_path = tmp_path / "kb.db"
        v = _view("sale.view_order_form", source_line=3, source_end_line=61)
        _write_xml(db_path, views=[v])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            single = kb.get_view("sale.view_order_form")
            module_views = kb.get_module_views("sale")
        assert single is not None
        assert single["source_end_line"] == 61
        assert single["source_end_line"] >= single["source_line"]
        assert module_views[0]["source_end_line"] == 61

    def test_action_ingestion_round_trip(self, tmp_path):
        db_path = tmp_path / "kb.db"
        a = _action("sale.action_orders")
        _write_xml(db_path, actions=[a])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            actions = kb.get_actions()
        assert len(actions) == 1
        assert actions[0]["xml_id"] == "sale.action_orders"

    def test_menu_ingestion_round_trip(self, tmp_path):
        db_path = tmp_path / "kb.db"
        m = _menu("sale.menu_root")
        _write_xml(db_path, menus=[m])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            menus = kb.get_menus()
        assert len(menus) == 1
        assert menus[0]["xml_id"] == "sale.menu_root"

    def test_second_write_clears_old_rows(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_xml(db_path, views=[_view("sale.view_a")])
        _write_xml(db_path, views=[_view("sale.view_b")])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            views = kb.get_views()
        xml_ids = {v["xml_id"] for v in views}
        assert "sale.view_a" not in xml_ids
        assert "sale.view_b" in xml_ids

    def test_duplicate_xml_id_uses_last_write(self, tmp_path):
        db_path = tmp_path / "kb.db"
        v1 = _view("sale.view_form", view_type="form")
        v2 = _view("sale.view_form", view_type="list")
        _write_xml(db_path, views=[v1, v2])
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            views = kb.get_views()
        assert len(views) == 1
        assert views[0]["view_type"] == "list"

    def test_get_view_missing_returns_none(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            assert kb.get_view("nonexistent.view") is None

    def test_stats_include_xml_counts(self, tmp_path):
        db_path = tmp_path / "kb.db"
        result = _write_xml(
            db_path,
            views=[_view("sale.view_form")],
            actions=[_action("sale.action")],
            menus=[_menu("sale.menu")],
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
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
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
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
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
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            assert kb.get_module_menu_count("mod_a") == 2

    def test_get_module_views_empty(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(db_path)
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            rows = kb.get_module_views("nonexistent_module")
        assert rows == []

    def test_get_module_load_order_returns_depth_and_load_index(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            modules={
                "base": {"origin": "odoo", "depends": [], "depth": 0, "load_index": 0},
                "sale": {"origin": "odoo", "depends": ["base"], "depth": 1, "load_index": 1},
            },
        )
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            lo = kb.get_module_load_order()
        assert lo["base"] == (0, 0)
        assert lo["sale"] == (1, 1)

    def test_get_module_load_order_null_when_not_stamped(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write(
            db_path,
            modules={"base": {"origin": "odoo", "depends": []}},
        )
        with KBReader(db_path, repo_ids=[_REPO_ID]) as kb:
            lo = kb.get_module_load_order()
        assert "base" in lo
        depth, load_index = lo["base"]
        assert depth is None
        assert load_index is None
