# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for build_class_chain, compute_mro, and merge_fields."""

import json
import sqlite3
from pathlib import Path

from oops_engine.inheritance import build_class_chain, compute_mro, merge_fields
from oops_engine.store import KBReader

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
            repo_id TEXT NOT NULL DEFAULT 'test',
            name TEXT PRIMARY KEY, origin TEXT,
            depends TEXT DEFAULT '[]',
            application INTEGER DEFAULT 0,
            app TEXT,
            depth INTEGER,
            load_index INTEGER
        );
        CREATE TABLE model_origins (
            repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, module TEXT, origin TEXT, role TEXT,
            model_type TEXT DEFAULT 'model',
            inherit_json TEXT DEFAULT '[]',
            inherits_json TEXT DEFAULT '{}',
            source_file TEXT, source_line INTEGER,
            description TEXT, import_index INTEGER,
            PRIMARY KEY (model, module)
        );
        CREATE TABLE symbols (
            repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, name TEXT, kind TEXT,
            origin TEXT, module TEXT,
            source_file TEXT, source_line INTEGER,
            source_end_line INTEGER,
            field_type TEXT, section TEXT,
            import_index INTEGER, attrs_json TEXT,
            has_super INTEGER,
            PRIMARY KEY (model, name, kind, module)
        );
        CREATE TABLE field_refs (
            repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, field_name TEXT, module TEXT,
            kwarg TEXT, target_method TEXT,
            PRIMARY KEY (model, field_name, module, kwarg)
        );
        INSERT INTO meta VALUES ('schema_version', '9');
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
    _MO_SQL = "INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
    con.executemany(
        _MO_SQL,
        [
            ("test", "res.partner", "base", "odoo", "create", "model",
             "[]", "{}", "base/models/res_partner.py", 10, None, 0),
            ("test", "res.partner", "mail", "odoo", "extend", "model",
             "[]", "{}", "mail/models/res_partner.py", 5, None, 0),
            ("test", "res.partner", "custom", "apik", "extend", "model",
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
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("res.partner", reader, {})
        assert len(chain) == 3
        load_indices = [r["load_index"] for r in chain]
        assert load_indices == sorted(load_indices)

    def test_load_order_override(self, tmp_path):
        db_path = _make_db(tmp_path)
        # Reverse load order: custom=0, mail=1, base=2
        load_order = {"custom": (0, 0), "mail": (1, 1), "base": (2, 2)}
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("res.partner", reader, load_order)
        assert chain[0]["module"] == "custom"
        assert chain[1]["module"] == "mail"
        assert chain[2]["module"] == "base"

    def test_inherit_field_parsed(self, tmp_path):
        db_path = _make_db(tmp_path)
        with KBReader(db_path, repo_ids=["test"]) as reader:
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
            CREATE TABLE modules (repo_id TEXT NOT NULL DEFAULT 'test',
            name TEXT PRIMARY KEY, origin TEXT,
                depends TEXT DEFAULT '[]', application INTEGER DEFAULT 0,
                app TEXT, depth INTEGER, load_index INTEGER);
            CREATE TABLE model_origins (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, module TEXT, origin TEXT,
                role TEXT, model_type TEXT DEFAULT 'model',
                inherit_json TEXT DEFAULT '[]', inherits_json TEXT DEFAULT '{}',
                source_file TEXT, source_line INTEGER, description TEXT,
                import_index INTEGER, PRIMARY KEY (model, module));
            CREATE TABLE symbols (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, name TEXT, kind TEXT,
                origin TEXT, module TEXT, source_file TEXT, source_line INTEGER,
                source_end_line INTEGER, field_type TEXT, section TEXT,
                import_index INTEGER, attrs_json TEXT,
                PRIMARY KEY (model, name, kind, module));
            CREATE TABLE field_refs (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, field_name TEXT, module TEXT,
                kwarg TEXT, target_method TEXT,
                PRIMARY KEY (model, field_name, module, kwarg));
            INSERT INTO meta VALUES ('schema_version', '8');
        """)
        con.executemany(
            "INSERT INTO modules (name, origin, depth, load_index) VALUES (?,?,?,?)",
            [("a_mod", "odoo", 1, 5), ("b_mod", "odoo", 1, 5)],
        )
        con.executemany(
            "INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("test", "test.model", "a_mod", "odoo", "extend", "model", "[]", "{}", "a.py", 1, None, 1),
                ("test", "test.model", "b_mod", "odoo", "create", "model", "[]", "{}", "b.py", 1, None, 0),
            ],
        )
        con.commit()
        con.close()
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("test.model", reader, {})
        # b_mod has import_index=0, should come first
        assert chain[0]["module"] == "b_mod"
        assert chain[1]["module"] == "a_mod"


class TestMRO:
    def test_single_inherit_reversed(self, tmp_path):
        db_path = _make_db(tmp_path)
        with KBReader(db_path, repo_ids=["test"]) as reader:
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
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("res.partner", reader, {})
            mro = compute_mro(chain)
            fields = merge_fields(mro, reader)
        assert "email" in fields
        # custom module overrides required=True; it's later in load order
        assert fields["email"]["attrs"].get("required") is True
        assert fields["email"]["sources"]["required"][0] == "custom"

    def test_base_field_present(self, tmp_path):
        db_path = _make_db(tmp_path)
        with KBReader(db_path, repo_ids=["test"]) as reader:
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
            CREATE TABLE modules (repo_id TEXT NOT NULL DEFAULT 'test',
            name TEXT PRIMARY KEY, origin TEXT,
                depends TEXT DEFAULT '[]', application INTEGER DEFAULT 0,
                app TEXT, depth INTEGER, load_index INTEGER);
            CREATE TABLE model_origins (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, module TEXT, origin TEXT,
                role TEXT, model_type TEXT DEFAULT 'model',
                inherit_json TEXT DEFAULT '[]', inherits_json TEXT DEFAULT '{}',
                source_file TEXT, source_line INTEGER, description TEXT,
                import_index INTEGER, PRIMARY KEY (model, module));
            CREATE TABLE symbols (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, name TEXT, kind TEXT,
                origin TEXT, module TEXT, source_file TEXT, source_line INTEGER,
                source_end_line INTEGER, field_type TEXT, section TEXT,
                import_index INTEGER, attrs_json TEXT,
                PRIMARY KEY (model, name, kind, module));
            CREATE TABLE field_refs (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, field_name TEXT, module TEXT,
                kwarg TEXT, target_method TEXT,
                PRIMARY KEY (model, field_name, module, kwarg));
            INSERT INTO meta VALUES ('schema_version', '8');
        """)
        con.executemany(
            "INSERT INTO modules (name, origin, depth, load_index) VALUES (?,?,?,?)",
            [("base", "odoo", 0, 0), ("ext", "apik", 1, 1)],
        )
        con.executemany(
            "INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("test", "my.model", "base", "odoo", "create", "model", "[]", "{}", "f.py", 1, None, 0),
                ("test", "my.model", "ext", "apik", "extend", "model", "[]", "{}", "g.py", 1, None, 0),
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
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("my.model", reader, {})
            mro = compute_mro(chain)
            fields = merge_fields(mro, reader)
        sel = fields["state"]["attrs"]["selection"]
        # selection_add ["c"] should appear first (load order: ext at index 1)
        assert sel[0] == ["c", "C"]
        assert ["a", "A"] in sel
        assert ["b", "B"] in sel


# ---------------------------------------------------------------------------
# Multi-inherit / prototype C3 fixtures
# ---------------------------------------------------------------------------

def _make_diamond_db(tmp_path: Path) -> Path:
    """Diamond inheritance: base ← a, base ← b, c ← (a, b).

    Modules: base_mod(0) → a_mod(1) → b_mod(2) → c_mod(3)
    Models:
      base.model  created in base_mod
      a.model     prototype from base.model  (a_mod)
      b.model     prototype from base.model  (b_mod)
      c.model     creates with _inherit=[a.model, b.model]  (c_mod)
    """
    db_path = tmp_path / "diamond.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE modules (
            repo_id TEXT NOT NULL DEFAULT 'test',
            name TEXT PRIMARY KEY, origin TEXT,
            depends TEXT DEFAULT '[]',
            application INTEGER DEFAULT 0,
            app TEXT, depth INTEGER, load_index INTEGER
        );
        CREATE TABLE model_origins (
            repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, module TEXT, origin TEXT, role TEXT,
            model_type TEXT DEFAULT 'model',
            inherit_json TEXT DEFAULT '[]',
            inherits_json TEXT DEFAULT '{}',
            source_file TEXT, source_line INTEGER,
            description TEXT, import_index INTEGER,
            PRIMARY KEY (model, module)
        );
        CREATE TABLE symbols (
            repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, name TEXT, kind TEXT,
            origin TEXT, module TEXT,
            source_file TEXT, source_line INTEGER,
            source_end_line INTEGER,
            field_type TEXT, section TEXT,
            import_index INTEGER, attrs_json TEXT,
            has_super INTEGER,
            PRIMARY KEY (model, name, kind, module)
        );
        CREATE TABLE field_refs (
            repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, field_name TEXT, module TEXT,
            kwarg TEXT, target_method TEXT,
            PRIMARY KEY (model, field_name, module, kwarg)
        );
        INSERT INTO meta VALUES ('schema_version', '9');
    """)
    con.executemany(
        "INSERT INTO modules (name, origin, depends, depth, load_index) VALUES (?,?,?,?,?)",
        [
            ("base_mod", "odoo", "[]", 0, 0),
            ("a_mod",    "odoo", '["base_mod"]', 1, 1),
            ("b_mod",    "odoo", '["base_mod"]', 1, 2),
            ("c_mod",    "apik", '["a_mod","b_mod"]', 2, 3),
        ],
    )
    rows = [
        ("test", "base.model", "base_mod", "odoo", "create", "model", "[]", "{}", "f.py", 1, None, 0),
        ("test", "a.model", "a_mod", "odoo", "prototype", "model", '["base.model"]', "{}", "f.py", 1, None, 0),
        ("test", "b.model", "b_mod", "odoo", "prototype", "model", '["base.model"]', "{}", "f.py", 1, None, 0),
        ("test", "c.model", "c_mod", "apik", "create", "model", '["a.model","b.model"]', "{}", "f.py", 1, None, 0),
    ]
    con.executemany("INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return db_path


class TestMROC3:
    def test_diamond_c3_order(self, tmp_path):
        """c.model MRO must be [c, a, b, base] (classic diamond C3)."""
        db_path = _make_diamond_db(tmp_path)
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("c.model", reader, {})
            mro = compute_mro(chain, reader=reader, load_order={})
        model_names = [r["model"] for r in mro]
        assert model_names == ["c.model", "a.model", "b.model", "base.model"]

    def test_prototype_mro_includes_parent(self, tmp_path):
        """a.model MRO must be [a, base]."""
        db_path = _make_diamond_db(tmp_path)
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("a.model", reader, {})
            mro = compute_mro(chain, reader=reader, load_order={})
        model_names = [r["model"] for r in mro]
        assert model_names == ["a.model", "base.model"]

    def test_single_inherit_unchanged_with_reader(self, tmp_path):
        """Passing reader to a single-inherit chain must not change MRO."""
        db_path = _make_diamond_db(tmp_path)
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("base.model", reader, {})
            mro_no_reader = compute_mro(chain)
            mro_with_reader = compute_mro(chain, reader=reader, load_order={})
        assert [r["module"] for r in mro_no_reader] == [r["module"] for r in mro_with_reader]

    def test_cycle_guard_does_not_infinite_loop(self, tmp_path):
        """Cyclic _inherit references must not cause infinite recursion."""
        db_path = tmp_path / "cycle.db"
        con = sqlite3.connect(str(db_path))
        con.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE modules (repo_id TEXT NOT NULL DEFAULT 'test',
            name TEXT PRIMARY KEY, origin TEXT,
                depends TEXT DEFAULT '[]', application INTEGER DEFAULT 0,
                app TEXT, depth INTEGER, load_index INTEGER);
            CREATE TABLE model_origins (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, module TEXT, origin TEXT,
                role TEXT, model_type TEXT DEFAULT 'model',
                inherit_json TEXT DEFAULT '[]', inherits_json TEXT DEFAULT '{}',
                source_file TEXT, source_line INTEGER, description TEXT,
                import_index INTEGER, PRIMARY KEY (model, module));
            CREATE TABLE symbols (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, name TEXT, kind TEXT,
                origin TEXT, module TEXT, source_file TEXT, source_line INTEGER,
                source_end_line INTEGER, field_type TEXT, section TEXT,
                import_index INTEGER, attrs_json TEXT, has_super INTEGER,
                PRIMARY KEY (model, name, kind, module));
            CREATE TABLE field_refs (repo_id TEXT NOT NULL DEFAULT 'test',
            model TEXT, field_name TEXT, module TEXT,
                kwarg TEXT, target_method TEXT,
                PRIMARY KEY (model, field_name, module, kwarg));
            INSERT INTO meta VALUES ('schema_version', '9');
        """)
        con.executemany(
            "INSERT INTO modules (name, origin, depth, load_index) VALUES (?,?,?,?)",
            [("mod_x", "odoo", 0, 0), ("mod_y", "odoo", 1, 1)],
        )
        con.executemany(
            "INSERT INTO model_origins VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("test", "x.model", "mod_x", "odoo", "prototype", "model", '["y.model"]', "{}", "f.py", 1, None, 0),
                ("test", "y.model", "mod_y", "odoo", "prototype", "model", '["x.model"]', "{}", "f.py", 1, None, 0),
            ],
        )
        con.commit()
        con.close()
        with KBReader(db_path, repo_ids=["test"]) as reader:
            chain = build_class_chain("x.model", reader, {})
            mro = compute_mro(chain, reader=reader, load_order={})
        # Must not raise; exact order is the fallback (reversed chain)
        assert len(mro) >= 1
