# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for build_class_chain, compute_mro, and merge_fields."""

import json
import sqlite3
from pathlib import Path

from oops.kb.inheritance import build_class_chain, compute_mro, merge_fields
from oops.kb.store import KBReader

# ---------------------------------------------------------------------------
# Minimal in-memory KB fixture
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> Path:
    """Create a minimal KB with three modules extending res.partner."""
    db_path = tmp_path / "kb.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE modules (
            name TEXT PRIMARY KEY, origin TEXT,
            depends TEXT DEFAULT '[]',
            application INTEGER DEFAULT 0,
            app TEXT,
            depth INTEGER,
            load_index INTEGER
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
    """)
    # Modules: base(depth=0,idx=0), mail(depth=1,idx=1), custom(depth=2,idx=2)
    con.executemany(
        "INSERT INTO modules (name, origin, depends, depth, load_index) VALUES (?,?,?,?,?)",
        [
            ("base", "odoo", "[]", 0, 0),
            ("mail", "odoo", '["base"]', 1, 1),
            ("custom", "apik", '["mail"]', 2, 2),
        ],
    )
    # Each module defines/extends res.partner
    _MO_SQL = "INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    con.executemany(
        _MO_SQL,
        [
            ("res.partner", "base", "odoo", "create", "model",
             "[]", "{}", "base/models/res_partner.py", 10, None, 0),
            ("res.partner", "mail", "odoo", "extend", "model",
             "[]", "{}", "mail/models/res_partner.py", 5, None, 0),
            ("res.partner", "custom", "apik", "extend", "model",
             "[]", "{}", "custom/models/res_partner.py", 3, None, 0),
        ],
    )
    # Fields
    _SYM_SQL = (
        "INSERT INTO symbols"
        " (model, name, kind, origin, module, source_file, source_line, import_index, attrs_json)"
        " VALUES (?,?,?,?,?,?,?,?,?)"
    )
    _char = {"type": "Char"}
    con.executemany(
        _SYM_SQL,
        [
            ("res.partner", "name", "field", "odoo", "base",
             "base/models/res_partner.py", 15, 0, json.dumps({**_char, "required": False})),
            ("res.partner", "email", "field", "odoo", "mail",
             "mail/models/res_partner.py", 10, 0, json.dumps({**_char, "required": False})),
            ("res.partner", "email", "field", "apik", "custom",
             "custom/models/res_partner.py", 8, 0, json.dumps({**_char, "required": True})),
        ],
    )
    con.commit()
    con.close()
    return db_path


class TestClassChain:
    def test_load_index_ordering(self, tmp_path):
        db_path = _make_db(tmp_path)
        with KBReader(db_path) as reader:
            chain = build_class_chain("res.partner", reader, {})
        assert len(chain) == 3
        load_indices = [r["load_index"] for r in chain]
        assert load_indices == sorted(load_indices)

    def test_load_order_override(self, tmp_path):
        db_path = _make_db(tmp_path)
        # Reverse load order: custom=0, mail=1, base=2
        load_order = {"custom": (0, 0), "mail": (1, 1), "base": (2, 2)}
        with KBReader(db_path) as reader:
            chain = build_class_chain("res.partner", reader, load_order)
        assert chain[0]["module"] == "custom"
        assert chain[1]["module"] == "mail"
        assert chain[2]["module"] == "base"

    def test_inherit_field_parsed(self, tmp_path):
        db_path = _make_db(tmp_path)
        with KBReader(db_path) as reader:
            chain = build_class_chain("res.partner", reader, {})
        for r in chain:
            assert isinstance(r["inherit"], list)
            assert isinstance(r["inherits"], dict)

    def test_import_index_tiebreak(self, tmp_path):
        """Two modules at same load_index, different import_index."""
        db_path = tmp_path / "tie.db"
        con = sqlite3.connect(str(db_path))
        con.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE modules (name TEXT PRIMARY KEY, origin TEXT,
                depends TEXT DEFAULT '[]', application INTEGER DEFAULT 0,
                app TEXT, depth INTEGER, load_index INTEGER);
            CREATE TABLE model_origins (model TEXT, module TEXT, origin TEXT,
                role TEXT, model_type TEXT DEFAULT 'model',
                inherit_json TEXT DEFAULT '[]', inherits_json TEXT DEFAULT '{}',
                source_file TEXT, source_line INTEGER, description TEXT,
                import_index INTEGER, PRIMARY KEY (model, module));
            CREATE TABLE symbols (model TEXT, name TEXT, kind TEXT,
                origin TEXT, module TEXT, source_file TEXT, source_line INTEGER,
                source_end_line INTEGER, field_type TEXT, section TEXT,
                import_index INTEGER, attrs_json TEXT,
                PRIMARY KEY (model, name, kind, module));
            CREATE TABLE field_refs (model TEXT, field_name TEXT, module TEXT,
                kwarg TEXT, target_method TEXT,
                PRIMARY KEY (model, field_name, module, kwarg));
            INSERT INTO meta VALUES ('schema_version', '8');
        """)
        con.executemany(
            "INSERT INTO modules (name, origin, depth, load_index) VALUES (?,?,?,?)",
            [("a_mod", "odoo", 1, 5), ("b_mod", "odoo", 1, 5)],
        )
        con.executemany(
            "INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("test.model", "a_mod", "odoo", "extend", "model", "[]", "{}", "a.py", 1, None, 1),
                ("test.model", "b_mod", "odoo", "create", "model", "[]", "{}", "b.py", 1, None, 0),
            ],
        )
        con.commit()
        con.close()
        with KBReader(db_path) as reader:
            chain = build_class_chain("test.model", reader, {})
        # b_mod has import_index=0, should come first
        assert chain[0]["module"] == "b_mod"
        assert chain[1]["module"] == "a_mod"


class TestMRO:
    def test_single_inherit_reversed(self, tmp_path):
        db_path = _make_db(tmp_path)
        with KBReader(db_path) as reader:
            chain = build_class_chain("res.partner", reader, {})
        mro = compute_mro(chain)
        assert len(mro) == len(chain)
        # MRO is most-derived first = reverse of chain (earliest-loaded first)
        assert [r["module"] for r in mro] == [r["module"] for r in reversed(chain)]

    def test_empty_chain(self):
        assert compute_mro([]) == []

    def test_single_entry(self):
        chain = [{"inherit": [], "role": "create", "module": "base", "load_index": 0}]
        mro = compute_mro(chain)
        assert mro == chain


class TestFieldMerge:
    def test_required_override(self, tmp_path):
        db_path = _make_db(tmp_path)
        with KBReader(db_path) as reader:
            chain = build_class_chain("res.partner", reader, {})
            mro = compute_mro(chain)
            fields = merge_fields(mro, reader)
        assert "email" in fields
        # custom module overrides required=True; it's later in load order
        assert fields["email"]["attrs"].get("required") is True
        assert fields["email"]["sources"]["required"][0] == "custom"

    def test_base_field_present(self, tmp_path):
        db_path = _make_db(tmp_path)
        with KBReader(db_path) as reader:
            chain = build_class_chain("res.partner", reader, {})
            mro = compute_mro(chain)
            fields = merge_fields(mro, reader)
        assert "name" in fields
        # "name" only defined in base with required=False; source must be base
        assert fields["name"]["sources"]["required"][0] == "base"

    def test_selection_add_accumulation(self, tmp_path):
        db_path = tmp_path / "sel.db"
        con = sqlite3.connect(str(db_path))
        con.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE modules (name TEXT PRIMARY KEY, origin TEXT,
                depends TEXT DEFAULT '[]', application INTEGER DEFAULT 0,
                app TEXT, depth INTEGER, load_index INTEGER);
            CREATE TABLE model_origins (model TEXT, module TEXT, origin TEXT,
                role TEXT, model_type TEXT DEFAULT 'model',
                inherit_json TEXT DEFAULT '[]', inherits_json TEXT DEFAULT '{}',
                source_file TEXT, source_line INTEGER, description TEXT,
                import_index INTEGER, PRIMARY KEY (model, module));
            CREATE TABLE symbols (model TEXT, name TEXT, kind TEXT,
                origin TEXT, module TEXT, source_file TEXT, source_line INTEGER,
                source_end_line INTEGER, field_type TEXT, section TEXT,
                import_index INTEGER, attrs_json TEXT,
                PRIMARY KEY (model, name, kind, module));
            CREATE TABLE field_refs (model TEXT, field_name TEXT, module TEXT,
                kwarg TEXT, target_method TEXT,
                PRIMARY KEY (model, field_name, module, kwarg));
            INSERT INTO meta VALUES ('schema_version', '8');
        """)
        con.executemany(
            "INSERT INTO modules (name, origin, depth, load_index) VALUES (?,?,?,?)",
            [("base", "odoo", 0, 0), ("ext", "apik", 1, 1)],
        )
        con.executemany(
            "INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("my.model", "base", "odoo", "create", "model", "[]", "{}", "f.py", 1, None, 0),
                ("my.model", "ext", "apik", "extend", "model", "[]", "{}", "g.py", 1, None, 0),
            ],
        )
        base_attrs = json.dumps({"type": "Selection", "selection": [["a", "A"], ["b", "B"]]})
        ext_attrs = json.dumps({"selection_add": [["c", "C"]]})
        _sym_sql = (
            "INSERT INTO symbols"
            " (model, name, kind, origin, module, source_file, source_line, import_index, attrs_json)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
        )
        con.executemany(
            _sym_sql,
            [
                ("my.model", "state", "field", "odoo", "base", "f.py", 5, 0, base_attrs),
                ("my.model", "state", "field", "apik", "ext", "g.py", 3, 0, ext_attrs),
            ],
        )
        con.commit()
        con.close()
        with KBReader(db_path) as reader:
            chain = build_class_chain("my.model", reader, {})
            mro = compute_mro(chain)
            fields = merge_fields(mro, reader)
        sel = fields["state"]["attrs"]["selection"]
        # selection_add ["c"] should appear first (load order: ext at index 1)
        assert sel[0] == ["c", "C"]
        assert ["a", "A"] in sel
        assert ["b", "B"] in sel
