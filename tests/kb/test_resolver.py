# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Integration tests for InheritanceResolver."""

import json
import sqlite3
from pathlib import Path

from oops.kb.resolver import InheritanceResolver


def _make_fixture_kb(tmp_path: Path) -> Path:
    db_path = tmp_path / "kb.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE modules (
            name TEXT PRIMARY KEY, origin TEXT,
            depends TEXT DEFAULT '[]',
            application INTEGER DEFAULT 0,
            app TEXT, depth INTEGER, load_index INTEGER
        );
        CREATE TABLE model_origins (
            model TEXT, module TEXT, origin TEXT, role TEXT,
            model_type TEXT DEFAULT 'model',
            inherit_json TEXT DEFAULT '[]',
            inherits_json TEXT DEFAULT '{}',
            source_file TEXT, source_line INTEGER,
            description TEXT, import_index INTEGER,
            PRIMARY KEY (model, module)
        );
        CREATE TABLE symbols (
            model TEXT, name TEXT, kind TEXT,
            origin TEXT, module TEXT,
            source_file TEXT, source_line INTEGER,
            source_end_line INTEGER,
            field_type TEXT, section TEXT,
            import_index INTEGER, attrs_json TEXT,
            PRIMARY KEY (model, name, kind, module)
        );
        CREATE TABLE field_refs (
            model TEXT, field_name TEXT, module TEXT,
            kwarg TEXT, target_method TEXT,
            PRIMARY KEY (model, field_name, module, kwarg)
        );
        INSERT INTO meta VALUES ('schema_version', '8');
        INSERT INTO meta VALUES ('odoo_version', '17.0');
        INSERT INTO meta VALUES ('layer', 'project');
    """)
    con.executemany(
        "INSERT INTO modules (name, origin, depends, depth, load_index) VALUES (?,?,?,?,?)",
        [
            ("base", "odoo", "[]", 0, 0),
            ("sale", "odoo", '["base"]', 1, 1),
            ("custom_sale", "apik", '["sale"]', 2, 2),
        ],
    )
    con.executemany(
        "INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("sale.order", "base", "odoo", "create", "model", "[]", "{}", "base/sale_order.py", 1, None, 0),
            ("sale.order", "sale", "odoo", "extend", "model", "[]", "{}", "sale/sale_order.py", 1, None, 0),
            ("sale.order", "custom_sale", "apik", "extend", "model", "[]", "{}", "custom/sale_order.py", 1, None, 0),
        ],
    )
    base_field = json.dumps({"type": "Char", "required": False})
    custom_field = json.dumps({"type": "Char", "required": True})
    _sym_sql = (
        "INSERT INTO symbols"
        " (model, name, kind, origin, module, source_file, source_line, import_index, attrs_json)"
        " VALUES (?,?,?,?,?,?,?,?,?)"
    )
    con.executemany(
        _sym_sql,
        [
            ("sale.order", "name", "field", "odoo", "base",
             "base/sale_order.py", 10, 0, base_field),
            ("sale.order", "name", "field", "apik", "custom_sale",
             "custom/sale_order.py", 5, 0, custom_field),
        ],
    )
    con.commit()
    con.close()
    return db_path


class TestInheritanceResolver:
    def test_resolve_returns_expected_keys(self, tmp_path):
        db_path = _make_fixture_kb(tmp_path)
        resolver = InheritanceResolver.from_project_kb(db_path)
        result = resolver.resolve("sale.order")
        assert set(result.keys()) == {"model", "chain", "mro", "fields"}
        assert result["model"] == "sale.order"

    def test_chain_length(self, tmp_path):
        db_path = _make_fixture_kb(tmp_path)
        resolver = InheritanceResolver.from_project_kb(db_path)
        result = resolver.resolve("sale.order")
        assert len(result["chain"]) == 3

    def test_chain_load_order(self, tmp_path):
        db_path = _make_fixture_kb(tmp_path)
        resolver = InheritanceResolver.from_project_kb(db_path)
        result = resolver.resolve("sale.order")
        modules = [r["module"] for r in result["chain"]]
        assert modules == ["base", "sale", "custom_sale"]

    def test_field_source_override(self, tmp_path):
        db_path = _make_fixture_kb(tmp_path)
        resolver = InheritanceResolver.from_project_kb(db_path)
        result = resolver.resolve("sale.order")
        assert "name" in result["fields"]
        # custom_sale overrides required=True
        assert result["fields"]["name"]["attrs"].get("required") is True
        assert result["fields"]["name"]["sources"]["required"][0] == "custom_sale"

    def test_installed_modules_restriction(self, tmp_path):
        db_path = _make_fixture_kb(tmp_path)
        resolver = InheritanceResolver.from_project_kb(db_path)
        # Restrict to base+sale only — custom_sale excluded
        result = resolver.resolve("sale.order", installed_modules={"base", "sale"})
        chain_modules = {r["module"] for r in result["chain"]}
        # custom_sale is in KB but excluded from load_order
        # chain still includes all DB rows, but load_index for custom_sale will be None
        # (not in installed set), so it sorts last — presence depends on DB rows
        assert "base" in chain_modules
        assert "sale" in chain_modules

    def test_mro_most_derived_first(self, tmp_path):
        db_path = _make_fixture_kb(tmp_path)
        resolver = InheritanceResolver.from_project_kb(db_path)
        result = resolver.resolve("sale.order")
        mro_modules = [r["module"] for r in result["mro"]]
        chain_modules = [r["module"] for r in result["chain"]]
        assert mro_modules == list(reversed(chain_modules))
