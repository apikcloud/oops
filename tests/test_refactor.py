# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_refactor.py — tests/test_refactor.py

"""Tests for oops/commands/addons/refactor.py."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import libcst as cst
from click.testing import CliRunner
from oops.commands.addons.refactor import main
from oops.core.models import Result
from oops.io.refactor import (
    ClassInfo,
    SymbolInfo,
    _append_section,
    _build_docstring_stmt,
    _class_docstring_lines,
    _detect_super,
    _get_decorator_names,
    _has_class_docstring,
    _has_docstring,
    _is_class_docstring,
    _is_field_stmt_cst,
    _is_private_attr_stmt,
    _make_header,
    _method_docstring_lines,
    _strip_leading_lines,
    analyse_file,
    rewrite_file,
)
from oops.kb.scanner import (
    classify_method as _classify_method,
)
from oops.kb.scanner import (
    get_model_names as _get_model_names,
)
from oops.kb.scanner import (
    is_field_assignment as _is_field,
)
from oops.kb.scanner import (
    is_odoo_model_class as _is_odoo_class,
)
from oops.kb.store import KBReader, write_project_kb

# ---------------------------------------------------------------------------
# Shared test fixtures / source snippets
# ---------------------------------------------------------------------------

NEW_MODEL_SOURCE = textwrap.dedent("""\
    from odoo import fields, models


    class MyModel(models.Model):
        _name = 'my.new.model'

        name = fields.Char(string='Name')
        active = fields.Boolean(default=True)

        def action_open(self):
            pass

        def _compute_state(self):
            pass
""")

INHERIT_MODEL_SOURCE = textwrap.dedent("""\
    from odoo import fields, models


    class SaleOrder(models.Model):
        _inherit = 'sale.order'

        x_custom = fields.Char(string='Custom')
        partner_id = fields.Many2one('res.partner')

        def action_confirm(self):
            return super().action_confirm()
""")


# ---------------------------------------------------------------------------
# KB and module helpers
# ---------------------------------------------------------------------------


def _make_kb(
    db_path: Path,
    symbols: list[dict] | None = None,
    modules: dict | None = None,
    model_origins: list[dict] | None = None,
) -> None:
    scan_results = [{
        "modules": modules or {},
        "symbols": symbols or [],
        "field_refs": [],
        "model_origins": model_origins or [],
    }]
    write_project_kb(
        db_path=db_path,
        odoo_version="17.0",
        project="test",
        scope=[],
        sources={"odoo": "/odoo"},
        scan_results=scan_results,
    )


def _kb_symbol(model: str, name: str, kind: str, module: str = "sale") -> dict:
    return {
        "model": model,
        "name": name,
        "kind": kind,
        "origin": "odoo",
        "module": module,
        "source_file": f"addons/{module}/models/{model.replace('.', '_')}.py",
        "source_line": 10,
    }


def _make_module(root: Path, name: str, model_files: dict[str, str]) -> Path:
    module_path = root / name
    models_dir = module_path / "models"
    models_dir.mkdir(parents=True)
    for filename, content in model_files.items():
        (models_dir / filename).write_text(content, encoding="utf-8")
    return module_path


# ---------------------------------------------------------------------------
# AST parse helpers
# ---------------------------------------------------------------------------


def _parse_class(src: str) -> ast.ClassDef:
    tree = ast.parse(textwrap.dedent(src))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))


def _parse_func(src: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(src))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))


def _class_body_stmts(src: str) -> list[ast.stmt]:
    """Parse `src` as a class body and return the statement list."""
    indented = "\n".join("    " + ln for ln in textwrap.dedent(src).splitlines())
    tree = ast.parse(f"class _F:\n{indented}")
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    return cls.body


# ---------------------------------------------------------------------------
# TestMakeHeader
# ---------------------------------------------------------------------------


class TestMakeHeader:
    def test_format(self):
        assert _make_header("COMPUTE METHODS") == "# === COMPUTE METHODS === #"

    def test_varies_by_name(self):
        assert _make_header("BASE FIELDS") == "# === BASE FIELDS === #"


# ---------------------------------------------------------------------------
# TestClassifyMethod
# ---------------------------------------------------------------------------


class TestClassifyMethod:
    def test_crud_create(self):
        assert _classify_method("create", []) == "CRUD METHODS"

    def test_crud_write(self):
        assert _classify_method("write", []) == "CRUD METHODS"

    def test_crud_unlink(self):
        assert _classify_method("unlink", []) == "CRUD METHODS"

    def test_crud_copy(self):
        assert _classify_method("copy", []) == "CRUD METHODS"

    def test_compute_via_api_depends(self):
        assert _classify_method("_compute_amount", ["api.depends"]) == "COMPUTE METHODS"

    def test_compute_via_bare_depends(self):
        assert _classify_method("_compute_partner", ["depends"]) == "COMPUTE METHODS"

    def test_onchange_decorator(self):
        assert _classify_method("_onchange_partner", ["api.onchange"]) == "ONCHANGE METHODS"

    def test_constrains_decorator(self):
        assert _classify_method("_check_value", ["constrains"]) == "CONSTRAINT METHODS"

    def test_action_prefix(self):
        assert _classify_method("action_confirm", []) == "ACTION METHODS"

    def test_underscore_prefix_is_helper(self):
        assert _classify_method("_validate", []) == "HELPER METHODS"

    def test_public_method_is_business(self):
        assert _classify_method("confirm", []) == "BUSINESS METHODS"

    def test_crud_wins_over_decorator(self):
        assert _classify_method("write", ["api.model"]) == "CRUD METHODS"


# ---------------------------------------------------------------------------
# TestIsOdooClass
# ---------------------------------------------------------------------------


class TestIsOdooClass:
    def test_models_model(self):
        assert _is_odoo_class(_parse_class("class Foo(models.Model): pass")) is True

    def test_transient_model(self):
        assert _is_odoo_class(_parse_class("class Foo(models.TransientModel): pass")) is True

    def test_abstract_model(self):
        assert _is_odoo_class(_parse_class("class Foo(models.AbstractModel): pass")) is True

    def test_plain_object(self):
        assert _is_odoo_class(_parse_class("class Foo(object): pass")) is False

    def test_no_bases(self):
        assert _is_odoo_class(_parse_class("class Foo: pass")) is False


# ---------------------------------------------------------------------------
# TestGetModelNames
# ---------------------------------------------------------------------------


class TestGetModelNames:
    def test_name_only(self):
        node = _parse_class("class Foo(models.Model):\n    _name = 'sale.order'")
        name, inherit = _get_model_names(node)
        assert name == "sale.order"
        assert inherit == []

    def test_inherit_string(self):
        node = _parse_class("class Foo(models.Model):\n    _inherit = 'sale.order'")
        name, inherit = _get_model_names(node)
        assert name is None
        assert inherit == ["sale.order"]

    def test_inherit_list(self):
        src = "class Foo(models.Model):\n    _inherit = ['sale.order', 'mail.thread']"
        node = _parse_class(src)
        name, inherit = _get_model_names(node)
        assert name is None
        assert inherit == ["sale.order", "mail.thread"]

    def test_both_name_and_inherit(self):
        src = "class Foo(models.Model):\n    _name = 'my.model'\n    _inherit = ['mail.thread']"
        node = _parse_class(src)
        name, inherit = _get_model_names(node)
        assert name == "my.model"
        assert inherit == ["mail.thread"]

    def test_no_attributes(self):
        node = _parse_class("class Foo(models.Model):\n    pass")
        name, inherit = _get_model_names(node)
        assert name is None
        assert inherit == []


# ---------------------------------------------------------------------------
# TestIsField
# ---------------------------------------------------------------------------


class TestIsField:
    def test_attribute_style_field(self):
        stmts = _class_body_stmts("partner_id = fields.Many2one('res.partner')")
        result = _is_field(stmts[0])
        assert result is not None
        assert result[0] == "partner_id"

    def test_bare_name_field(self):
        stmts = _class_body_stmts("name = Char(string='Name')")
        result = _is_field(stmts[0])
        assert result is not None
        assert result[0] == "name"

    def test_private_attr_is_not_field(self):
        stmts = _class_body_stmts("_name = 'sale.order'")
        assert _is_field(stmts[0]) is None

    def test_plain_assignment_is_not_field(self):
        stmts = _class_body_stmts("x = 1")
        assert _is_field(stmts[0]) is None

    def test_method_is_not_field(self):
        stmts = _class_body_stmts("def action_confirm(self): pass")
        assert _is_field(stmts[0]) is None


# ---------------------------------------------------------------------------
# TestHasDocstring
# ---------------------------------------------------------------------------


class TestHasDocstring:
    def test_with_docstring(self):
        src = 'def foo(self):\n    """Docstring."""\n    pass'
        assert _has_docstring(_parse_func(src)) is True

    def test_without_docstring(self):
        assert _has_docstring(_parse_func("def foo(self):\n    pass")) is False

    def test_comment_is_not_docstring(self):
        src = "def foo(self):\n    # comment\n    pass"
        assert _has_docstring(_parse_func(src)) is False


# ---------------------------------------------------------------------------
# TestHasClassDocstring
# ---------------------------------------------------------------------------


class TestHasClassDocstring:
    def test_with_docstring(self):
        src = 'class Foo:\n    """Class docstring."""\n    pass'
        assert _has_class_docstring(_parse_class(src)) is True

    def test_without_docstring(self):
        assert _has_class_docstring(_parse_class("class Foo:\n    _name = 'x'")) is False


# ---------------------------------------------------------------------------
# TestGetDecoratorNames
# ---------------------------------------------------------------------------


class TestGetDecoratorNames:
    def test_call_decorator_returns_attr_name(self):
        # @api.depends('...') is an ast.Call — only 'depends' is extracted, not 'api.depends'
        src = textwrap.dedent("""\
            class C:
                @api.depends('partner_id')
                def compute(self): pass
        """)
        names = _get_decorator_names(_parse_func(src))
        assert "depends" in names

    def test_bare_attribute_decorator_returns_qualified_name(self):
        # @api.depends (no call) is an ast.Attribute — both 'depends' and 'api.depends' added
        src = "class C:\n    @api.depends\n    def compute(self): pass"
        names = _get_decorator_names(_parse_func(src))
        assert "depends" in names
        assert "api.depends" in names

    def test_simple_decorator(self):
        src = "class C:\n    @property\n    def name(self): pass"
        assert "property" in _get_decorator_names(_parse_func(src))

    def test_no_decorators(self):
        assert _get_decorator_names(_parse_func("def foo(self): pass")) == []


# ---------------------------------------------------------------------------
# TestDetectSuper
# ---------------------------------------------------------------------------


class TestDetectSuper:
    def test_detects_super_call_and_method_name(self):
        src = textwrap.dedent("""\
            class Foo:
                def write(self, vals):
                    return super().write(vals)
        """)
        has_super, methods = _detect_super(src, "write")
        assert has_super is True
        assert "write" in methods

    def test_no_super_call(self):
        src = textwrap.dedent("""\
            class Foo:
                def write(self, vals):
                    pass
        """)
        has_super, methods = _detect_super(src, "write")
        assert has_super is False
        assert methods == []

    def test_wrong_method_name_returns_false(self):
        src = textwrap.dedent("""\
            class Foo:
                def write(self, vals):
                    return super().write(vals)
        """)
        has_super, _ = _detect_super(src, "create")
        assert has_super is False

    def test_invalid_syntax_returns_false(self):
        has_super, methods = _detect_super("not valid python {{{{", "foo")
        assert has_super is False
        assert methods == []


# ---------------------------------------------------------------------------
# TestMethodDocstringLines
# ---------------------------------------------------------------------------


class TestMethodDocstringLines:
    def _sym(self, *, name="do_thing", kb_entry=None, is_override=False) -> SymbolInfo:
        return SymbolInfo(
            name=name,
            kind="method",
            section="BUSINESS METHODS",
            lineno=10,
            kb_entry=kb_entry,
            is_override=is_override,
        )

    def _kb_entry(self, module: str = "sale") -> dict:
        return {
            "origin": "odoo",
            "module": module,
            "source_file": f"addons/{module}/models/model.py",
            "source_line": 42,
        }

    def test_new_method_has_note_with_business_logic_todo(self):
        lines = _method_docstring_lines(self._sym())
        joined = "\n".join(lines)
        assert "Note:" in joined
        assert "business logic" in joined

    def test_inherit_method_starts_with_inherit_prefix(self):
        lines = _method_docstring_lines(self._sym(kb_entry=self._kb_entry()))
        joined = "\n".join(lines)
        assert "Inherit sale.do_thing" in joined
        assert "Source:" in joined

    def test_override_method_has_warning_about_super(self):
        lines = _method_docstring_lines(self._sym(kb_entry=self._kb_entry(), is_override=True))
        joined = "\n".join(lines)
        assert "Override sale.do_thing" in joined
        assert "Warning:" in joined
        assert "super()" in joined

    def test_all_variants_have_args_and_returns_sections(self):
        variants = [
            self._sym(),
            self._sym(kb_entry=self._kb_entry()),
            self._sym(kb_entry=self._kb_entry(), is_override=True),
        ]
        for sym in variants:
            joined = "\n".join(_method_docstring_lines(sym))
            assert "Args:" in joined, f"Args: missing for {sym}"
            assert "Returns:" in joined, f"Returns: missing for {sym}"


# ---------------------------------------------------------------------------
# TestClassDocstringLines
# ---------------------------------------------------------------------------


class TestClassDocstringLines:
    def test_contains_model_name(self):
        ci = ClassInfo(
            class_name="SaleOrder",
            model_name="sale.order",
            inherit=[],
            is_new_model=True,
            lineno=1,
        )
        assert any("sale.order" in ln for ln in _class_docstring_lines(ci))

    def test_fallback_when_model_name_is_none(self):
        ci = ClassInfo(
            class_name="SaleOrder",
            model_name=None,
            inherit=["sale.order"],
            is_new_model=True,
            lineno=1,
        )
        assert any("unknown.model" in ln for ln in _class_docstring_lines(ci))


# ---------------------------------------------------------------------------
# TestCSTPredicates
# ---------------------------------------------------------------------------


def _cst_class_stmts(src: str) -> list[cst.BaseStatement]:
    module = cst.parse_module(textwrap.dedent(src))
    cls = next(n for n in module.body if isinstance(n, cst.ClassDef))
    return list(cls.body.body)


class TestCSTPredicates:
    def test_is_class_docstring_true(self):
        stmts = _cst_class_stmts('class C:\n    """Docstring"""\n    pass\n')
        assert _is_class_docstring(stmts[0]) is True

    def test_is_class_docstring_false_for_assignment(self):
        stmts = _cst_class_stmts("class C:\n    _name = 'x'\n")
        assert _is_class_docstring(stmts[0]) is False

    def test_is_private_attr_stmt_true(self):
        stmts = _cst_class_stmts("class C:\n    _name = 'sale.order'\n")
        assert _is_private_attr_stmt(stmts[0]) is True

    def test_is_private_attr_stmt_false_for_public(self):
        stmts = _cst_class_stmts("class C:\n    name = 'x'\n")
        assert _is_private_attr_stmt(stmts[0]) is False

    def test_is_field_stmt_cst_attribute_style(self):
        stmts = _cst_class_stmts("class C:\n    partner_id = fields.Many2one('res.partner')\n")
        assert _is_field_stmt_cst(stmts[0]) is True

    def test_is_field_stmt_cst_bare_name(self):
        stmts = _cst_class_stmts("class C:\n    name = Char(string='Name')\n")
        assert _is_field_stmt_cst(stmts[0]) is True

    def test_is_field_stmt_cst_false_for_generic_call(self):
        stmts = _cst_class_stmts("class C:\n    x = some_func()\n")
        assert _is_field_stmt_cst(stmts[0]) is False


# ---------------------------------------------------------------------------
# TestBuildDocstringStmt
# ---------------------------------------------------------------------------


class TestBuildDocstringStmt:
    def test_returns_simple_statement_line(self):
        stmt = _build_docstring_stmt(["", "Summary.", ""])
        assert isinstance(stmt, cst.SimpleStatementLine)

    def test_content_is_triple_quoted(self):
        stmt = _build_docstring_stmt(["", "Hello.", ""])
        code = cst.parse_module("").with_changes(body=[stmt]).code
        assert '"""' in code
        assert "Hello." in code


# ---------------------------------------------------------------------------
# TestAppendSection
# ---------------------------------------------------------------------------


class TestAppendSection:
    def _stmt(self, code: str) -> cst.BaseStatement:
        return cst.parse_module(code + "\n").body[0]

    def test_does_nothing_for_empty_items(self):
        target: list = []
        _append_section("BASE FIELDS", [], target)
        assert target == []

    def test_adds_header_comment_to_first_item(self):
        stmt = self._stmt("x = 1")
        target: list = []
        _append_section("BASE FIELDS", [stmt], target)
        assert len(target) == 1
        comment_lines = [ln for ln in target[0].leading_lines if ln.comment is not None]
        assert any("BASE FIELDS" in ln.comment.value for ln in comment_lines)

    def test_second_item_does_not_get_header(self):
        s1, s2 = self._stmt("x = 1"), self._stmt("y = 2")
        target: list = []
        _append_section("BASE FIELDS", [s1, s2], target)
        assert len(target) == 2
        comment_lines = [ln for ln in target[1].leading_lines if ln.comment is not None]
        assert not any("BASE FIELDS" in ln.comment.value for ln in comment_lines)


# ---------------------------------------------------------------------------
# TestStripLeadingLines
# ---------------------------------------------------------------------------


class TestStripLeadingLines:
    def test_removes_blank_lines(self):
        stmt = cst.parse_module("x = 1\n").body[0]
        stmt_with = stmt.with_changes(leading_lines=[cst.EmptyLine(), cst.EmptyLine()])
        assert list(_strip_leading_lines(stmt_with).leading_lines) == []

    def test_idempotent_when_already_empty(self):
        stmt = cst.parse_module("x = 1\n").body[0]
        assert list(_strip_leading_lines(stmt).leading_lines) == []


# ---------------------------------------------------------------------------
# TestAnalyseFile — integration with real KB
# ---------------------------------------------------------------------------


class TestAnalyseFile:
    def _empty_kb(self, tmp_path: Path) -> Path:
        kb_path = tmp_path / "empty.db"
        _make_kb(kb_path)
        return kb_path

    def _sale_kb(self, tmp_path: Path) -> Path:
        kb_path = tmp_path / "sale.db"
        _make_kb(
            kb_path,
            modules={"sale": {"origin": "odoo", "depends": []}},
            symbols=[
                _kb_symbol("sale.order", "partner_id", "field"),
                _kb_symbol("sale.order", "action_confirm", "method"),
            ],
        )
        return kb_path

    def test_non_odoo_file_returns_empty(self, tmp_path):
        py_file = tmp_path / "helper.py"
        py_file.write_text("class Helper:\n    pass\n")
        with KBReader(self._empty_kb(tmp_path)) as kb:
            assert analyse_file(py_file, kb, {}, "mymodule") == []

    def test_detects_new_model_class(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            result = analyse_file(py_file, kb, {}, "mymodule")
        assert len(result) == 1
        ci = result[0]
        assert ci.class_name == "MyModel"
        assert ci.model_name == "my.new.model"
        assert ci.is_new_model is True

    def test_new_model_fields_go_to_base_fields(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            [ci] = analyse_file(py_file, kb, {}, "mymodule")
        field_syms = [s for s in ci.symbols if s.kind == "field"]
        assert field_syms
        assert all(s.section == "BASE FIELDS" for s in field_syms)

    def test_new_model_methods_classified_correctly(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            [ci] = analyse_file(py_file, kb, {}, "mymodule")
        method_map = {s.name: s for s in ci.symbols if s.kind == "method"}
        assert method_map["action_open"].section == "ACTION METHODS"
        assert method_map["_compute_state"].section == "HELPER METHODS"

    def test_inherited_known_field_section(self, tmp_path):
        py_file = tmp_path / "sale_order.py"
        py_file.write_text(INHERIT_MODEL_SOURCE)
        kb_path = self._sale_kb(tmp_path)
        with KBReader(kb_path) as kb:
            modules_index = kb.get_modules()
            [ci] = analyse_file(py_file, kb, modules_index, "my_sale")
        field_map = {s.name: s for s in ci.symbols if s.kind == "field"}
        assert field_map["partner_id"].section == "INHERITED FIELDS"
        assert field_map["x_custom"].section == "NEW FIELDS"

    def test_method_with_super_is_not_override(self, tmp_path):
        py_file = tmp_path / "sale_order.py"
        py_file.write_text(INHERIT_MODEL_SOURCE)
        kb_path = self._sale_kb(tmp_path)
        with KBReader(kb_path) as kb:
            modules_index = kb.get_modules()
            [ci] = analyse_file(py_file, kb, modules_index, "my_sale")
        method_map = {s.name: s for s in ci.symbols if s.kind == "method"}
        confirm = method_map["action_confirm"]
        assert confirm.has_super is True
        assert confirm.is_override is False
        assert confirm.kb_entry is not None

    def test_method_end_lineno_populated(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            [ci] = analyse_file(py_file, kb, {}, "mymodule")
        methods = [s for s in ci.symbols if s.kind == "method"]
        assert methods
        for s in methods:
            assert s.end_lineno >= s.lineno > 0

    def test_syntax_error_file_returns_empty(self, tmp_path):
        py_file = tmp_path / "broken.py"
        py_file.write_text("def broken(:\n    pass")
        with KBReader(self._empty_kb(tmp_path)) as kb:
            assert analyse_file(py_file, kb, {}, "mymodule") == []


# ---------------------------------------------------------------------------
# TestRewriteFile — integration: source transformations
# ---------------------------------------------------------------------------


class TestRewriteFile:
    def _empty_kb(self, tmp_path: Path) -> Path:
        kb_path = tmp_path / "empty.db"
        _make_kb(kb_path)
        return kb_path

    def test_returns_original_when_no_classes(self, tmp_path):
        py_file = tmp_path / "helper.py"
        content = "def helper(): pass\n"
        py_file.write_text(content)
        assert rewrite_file(py_file, []) == content

    def test_injects_base_fields_header(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            classes = analyse_file(py_file, kb, {}, "mymodule")
        assert "# === BASE FIELDS === #" in rewrite_file(py_file, classes)

    def test_injects_method_section_header(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            classes = analyse_file(py_file, kb, {}, "mymodule")
        new_src = rewrite_file(py_file, classes)
        assert "# === ACTION METHODS === #" in new_src
        assert "# === HELPER METHODS === #" in new_src

    def test_injects_docstring_for_undocumented_method(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            classes = analyse_file(py_file, kb, {}, "mymodule")
        new_src = rewrite_file(py_file, classes)
        assert '"""' in new_src
        assert "# TODO:" in new_src

    def test_preserves_existing_docstring(self, tmp_path):
        source = textwrap.dedent("""\
            from odoo import fields, models


            class MyModel(models.Model):
                _name = 'my.model'

                def action_open(self):
                    \"\"\"Already documented.\"\"\"
                    pass
        """)
        py_file = tmp_path / "my_model.py"
        py_file.write_text(source)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            classes = analyse_file(py_file, kb, {}, "mymodule")
        new_src = rewrite_file(py_file, classes)
        assert "Already documented." in new_src
        assert new_src.count("Already documented.") == 1

    def test_private_attrs_appear_before_fields_section(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            classes = analyse_file(py_file, kb, {}, "mymodule")
        new_src = rewrite_file(py_file, classes)
        assert new_src.index("_name") < new_src.index("# === BASE FIELDS === #")

    def test_output_is_valid_python(self, tmp_path):
        py_file = tmp_path / "my_model.py"
        py_file.write_text(NEW_MODEL_SOURCE)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            classes = analyse_file(py_file, kb, {}, "mymodule")
        ast.parse(rewrite_file(py_file, classes))  # must not raise


# ---------------------------------------------------------------------------
# TestRefactorCLI — CLI integration
# ---------------------------------------------------------------------------


class TestRefactorCLI:
    def _runner(self) -> CliRunner:
        return CliRunner()

    def _setup(self, tmp_path: Path) -> tuple[Path, Path]:
        kb_path = tmp_path / "kb.db"
        _make_kb(kb_path)
        module_path = _make_module(tmp_path, "my_module", {"my_model.py": NEW_MODEL_SOURCE})
        return module_path, kb_path

    def test_exits_when_no_kb_found(self, tmp_path):
        module_path = _make_module(tmp_path, "my_module", {"model.py": NEW_MODEL_SOURCE})
        result = self._runner().invoke(main, [str(module_path), "--no-branch"])
        assert result.exit_code == 1

    def test_dry_run_does_not_modify_file(self, tmp_path):
        module_path, kb_path = self._setup(tmp_path)
        model_file = module_path / "models" / "my_model.py"
        original = model_file.read_text()
        self._runner().invoke(main, [str(module_path), "--kb", str(kb_path), "--dry-run"])
        assert model_file.read_text() == original

    def test_normal_run_rewrites_file(self, tmp_path):
        module_path, kb_path = self._setup(tmp_path)
        model_file = module_path / "models" / "my_model.py"
        original = model_file.read_text()
        result = self._runner().invoke(
            main, [str(module_path), "--kb", str(kb_path), "--no-branch", "--no-commit"]
        )
        assert result.exit_code == 0
        new_content = model_file.read_text()
        assert new_content != original
        assert "# === BASE FIELDS === #" in new_content

    def test_no_models_dir_exits_cleanly(self, tmp_path):
        module_path = tmp_path / "my_module"
        module_path.mkdir()
        kb_path = tmp_path / "kb.db"
        _make_kb(kb_path)
        result = self._runner().invoke(
            main, [str(module_path), "--kb", str(kb_path), "--no-branch", "--no-commit"]
        )
        assert result.exit_code == 0

    def test_no_py_files_exits_cleanly(self, tmp_path):
        module_path = tmp_path / "my_module"
        (module_path / "models").mkdir(parents=True)
        kb_path = tmp_path / "kb.db"
        _make_kb(kb_path)
        result = self._runner().invoke(
            main, [str(module_path), "--kb", str(kb_path), "--no-branch", "--no-commit"]
        )
        assert result.exit_code == 0

    def test_explicit_kb_path_used_directly(self, tmp_path):
        kb_path = tmp_path / "kb.db"
        _make_kb(kb_path)
        module_path = _make_module(tmp_path, "my_module", {"my_model.py": NEW_MODEL_SOURCE})
        result = self._runner().invoke(
            main, [str(module_path), "--kb", str(kb_path), "--no-branch", "--no-commit"]
        )
        assert result.exit_code == 0

    def test_symlinked_module_path_is_rejected(self, tmp_path):
        real_module = _make_module(
            tmp_path / ".third-party" / "owner" / "repo",
            "real_module",
            {"model.py": NEW_MODEL_SOURCE},
        )
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        symlink = repo_path / "real_module"
        symlink.symlink_to(real_module)

        kb_path = tmp_path / "kb.db"
        _make_kb(kb_path)

        result = self._runner().invoke(
            main, [str(symlink), "--kb", str(kb_path), "--no-branch"]
        )
        assert result.exit_code == 1
        assert "symlink" in result.output.lower()
        # Real module must not have been rewritten
        real_file = real_module / "models" / "model.py"
        assert real_file.read_text() == NEW_MODEL_SOURCE


# ---------------------------------------------------------------------------
# TestRefactorRebuild — Phase 4: --refresh and auto-rebuild logic
# ---------------------------------------------------------------------------


class TestRefactorRebuild:
    """Tests for the new rebuild-aware flow in oops refactor."""

    def _runner(self) -> CliRunner:
        return CliRunner()

    def _setup_module(self, tmp_path: Path) -> Path:
        return _make_module(tmp_path, "my_module", {"my_model.py": NEW_MODEL_SOURCE})

    def _patch_repo(self, monkeypatch, tmp_path: Path):
        """Mock require_repository so tests don't need a real git repo."""
        from unittest.mock import MagicMock

        fake_repo = MagicMock()
        fake_repo.git.checkout = MagicMock()
        monkeypatch.setattr(
            "oops.commands.addons.refactor.require_repository",
            lambda: (fake_repo, tmp_path),
        )
        return fake_repo, tmp_path

    def _patch_version(self, monkeypatch, version: str = "17.0"):
        from unittest.mock import MagicMock

        fake_info = MagicMock()
        fake_info.major_version = version
        monkeypatch.setattr(
            "oops.commands.addons.refactor.parse_odoo_version",
            lambda _p: fake_info,
        )

    def _patch_build(self, monkeypatch, kb_path: Path):
        """Mock build_project_kb to return kb_path without running the scanner."""
        calls: list = []
        monkeypatch.setattr(
            "oops.commands.addons.refactor.build_project_kb",
            lambda *a, **kw: (calls.append((a, kw)), Result(data=kb_path))[1],
        )
        return calls

    def test_stale_kb_triggers_auto_rebuild(self, tmp_path, monkeypatch):
        kb_path = tmp_path / ".oops-cache" / "kb.db"
        kb_path.parent.mkdir()
        _make_kb(kb_path)
        module_path = self._setup_module(tmp_path)

        self._patch_repo(monkeypatch, tmp_path)
        self._patch_version(monkeypatch)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.is_project_kb_stale",
            lambda _r, _v: (True, "no project KB at ..."),
        )
        build_calls = self._patch_build(monkeypatch, kb_path)
        (tmp_path / "installed_modules.txt").write_text("my_module\n")
        monkeypatch.setattr(
            "oops.commands.addons.refactor.read_installed_modules",
            lambda _r: type("M", (), {"modules": ["my_module"]})(),
        )
        monkeypatch.setattr(
            "oops.commands.addons.refactor.compute_root_drift",
            lambda _r, _m: ([], []),
        )

        result = self._runner().invoke(main, [str(module_path), "--no-branch"])
        assert result.exit_code == 0
        assert len(build_calls) == 1

    def test_fresh_kb_no_rebuild(self, tmp_path, monkeypatch):
        kb_path = tmp_path / ".oops-cache" / "kb.db"
        kb_path.parent.mkdir()
        _make_kb(kb_path)
        module_path = self._setup_module(tmp_path)

        self._patch_repo(monkeypatch, tmp_path)
        self._patch_version(monkeypatch)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.is_project_kb_stale",
            lambda _r, _v: (False, ""),
        )
        build_calls = self._patch_build(monkeypatch, kb_path)

        result = self._runner().invoke(main, [str(module_path), "--no-branch"])
        assert result.exit_code == 0
        assert len(build_calls) == 0

    def test_refresh_forces_rebuild_even_when_fresh(self, tmp_path, monkeypatch):
        kb_path = tmp_path / ".oops-cache" / "kb.db"
        kb_path.parent.mkdir()
        _make_kb(kb_path)
        module_path = self._setup_module(tmp_path)

        self._patch_repo(monkeypatch, tmp_path)
        self._patch_version(monkeypatch)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.is_project_kb_stale",
            lambda _r, _v: (False, ""),
        )
        build_calls = self._patch_build(monkeypatch, kb_path)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.read_installed_modules",
            lambda _r: type("M", (), {"modules": ["my_module"]})(),
        )
        monkeypatch.setattr(
            "oops.commands.addons.refactor.compute_root_drift",
            lambda _r, _m: ([], []),
        )

        result = self._runner().invoke(main, [str(module_path), "--no-branch", "--refresh"])
        assert result.exit_code == 0
        assert len(build_calls) == 1

    def test_stale_kb_no_installed_modules_errors(self, tmp_path, monkeypatch):
        module_path = self._setup_module(tmp_path)

        self._patch_repo(monkeypatch, tmp_path)
        self._patch_version(monkeypatch)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.is_project_kb_stale",
            lambda _r, _v: (True, "no project KB at ..."),
        )
        monkeypatch.setattr(
            "oops.commands.addons.refactor.read_installed_modules",
            lambda _r: None,
        )

        result = self._runner().invoke(main, [str(module_path), "--no-branch"])
        assert result.exit_code == 1
        assert "installed_modules.txt" in result.output

    def test_refresh_no_installed_modules_errors(self, tmp_path, monkeypatch):
        kb_path = tmp_path / ".oops-cache" / "kb.db"
        kb_path.parent.mkdir()
        _make_kb(kb_path)
        module_path = self._setup_module(tmp_path)

        self._patch_repo(monkeypatch, tmp_path)
        self._patch_version(monkeypatch)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.is_project_kb_stale",
            lambda _r, _v: (False, ""),
        )
        monkeypatch.setattr(
            "oops.commands.addons.refactor.read_installed_modules",
            lambda _r: None,
        )

        result = self._runner().invoke(main, [str(module_path), "--no-branch", "--refresh"])
        assert result.exit_code == 1
        assert "installed_modules.txt" in result.output

    def test_explicit_kb_skips_rebuild_logic(self, tmp_path, monkeypatch):
        kb_path = tmp_path / "explicit.db"
        _make_kb(kb_path)
        module_path = self._setup_module(tmp_path)

        # Ensure build is never called
        build_calls = self._patch_build(monkeypatch, kb_path)

        def _fail():
            raise AssertionError("require_repository should not be called for KB resolution")

        monkeypatch.setattr(
            "oops.commands.addons.refactor.require_repository",
            _fail,
        )

        result = self._runner().invoke(
            main, [str(module_path), "--kb", str(kb_path), "--no-branch", "--no-commit"]
        )
        assert result.exit_code == 0
        assert len(build_calls) == 0

    def test_missing_odoo_version_errors(self, tmp_path, monkeypatch):
        module_path = self._setup_module(tmp_path)

        self._patch_repo(monkeypatch, tmp_path)
        # parse_odoo_version raises OSError (file not found)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.parse_odoo_version",
            lambda _p: (_ for _ in ()).throw(FileNotFoundError("odoo_version.txt not found")),
        )

        result = self._runner().invoke(main, [str(module_path), "--no-branch"])
        assert result.exit_code == 1
        assert "odoo_version.txt" in result.output.lower() or "Odoo version" in result.output

    def test_drift_warnings_emitted_even_when_kb_fresh(self, tmp_path, monkeypatch):
        kb_path = tmp_path / ".oops-cache" / "kb.db"
        kb_path.parent.mkdir()
        _make_kb(kb_path)
        module_path = self._setup_module(tmp_path)

        self._patch_repo(monkeypatch, tmp_path)
        self._patch_version(monkeypatch)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.is_project_kb_stale",
            lambda _r, _v: (False, ""),
        )
        monkeypatch.setattr(
            "oops.commands.addons.refactor.read_installed_modules",
            lambda _r: type("M", (), {"modules": ["my_module", "ghost"]})(),
        )
        monkeypatch.setattr(
            "oops.commands.addons.refactor.compute_root_drift",
            lambda _r, _m: (["ghost"], []),
        )
        self._patch_build(monkeypatch, kb_path)

        result = self._runner().invoke(main, [str(module_path), "--no-branch"])
        assert result.exit_code == 0
        assert "ghost" in result.output

    def test_drift_silent_when_no_installed_modules_and_kb_fresh(self, tmp_path, monkeypatch):
        kb_path = tmp_path / ".oops-cache" / "kb.db"
        kb_path.parent.mkdir()
        _make_kb(kb_path)
        module_path = self._setup_module(tmp_path)

        self._patch_repo(monkeypatch, tmp_path)
        self._patch_version(monkeypatch)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.is_project_kb_stale",
            lambda _r, _v: (False, ""),
        )
        monkeypatch.setattr(
            "oops.commands.addons.refactor.read_installed_modules",
            lambda _r: None,
        )
        self._patch_build(monkeypatch, kb_path)

        result = self._runner().invoke(main, [str(module_path), "--no-branch"])
        assert result.exit_code == 0
        assert "no symlink" not in result.output.lower()
        assert "not in installed_modules" not in result.output.lower()


# ---------------------------------------------------------------------------
# TestRefactorCommit — Phase 1: per-module commit and --no-commit flag
# ---------------------------------------------------------------------------


class TestRefactorCommit:
    """Tests for the new --no-commit flag and per-module commit behaviour."""

    def _runner(self) -> CliRunner:
        return CliRunner()

    def _setup(self, tmp_path: Path) -> tuple[Path, Path]:
        kb_path = tmp_path / "kb.db"
        _make_kb(kb_path)
        module_path = _make_module(tmp_path, "my_module", {"my_model.py": NEW_MODEL_SOURCE})
        return module_path, kb_path

    def _patch_repo(self, monkeypatch, tmp_path: Path):
        from unittest.mock import MagicMock

        fake_repo = MagicMock()
        fake_repo.git.checkout = MagicMock()
        monkeypatch.setattr(
            "oops.commands.addons.refactor.require_repository",
            lambda: (fake_repo, tmp_path),
        )
        return fake_repo

    def _patch_commit(self, monkeypatch) -> list:
        calls: list = []
        monkeypatch.setattr(
            "oops.commands.addons.refactor.commit",
            lambda *a, **kw: calls.append((a, kw)),
        )
        return calls

    def test_no_commit_with_branch_creates_branch_but_no_commit(self, tmp_path, monkeypatch):
        module_path, kb_path = self._setup(tmp_path)
        fake_repo = self._patch_repo(monkeypatch, tmp_path)
        commit_calls = self._patch_commit(monkeypatch)

        result = self._runner().invoke(
            main, [str(module_path), "--kb", str(kb_path), "--no-commit"]
        )
        assert result.exit_code == 0
        fake_repo.git.checkout.assert_called_once_with("-b", "refactor/doc-my_module")
        assert len(commit_calls) == 0
        # Files must be staged even though no commit is made.
        fake_repo.index.add.assert_called_once()

    def test_no_commit_without_branch_does_nothing_to_git(self, tmp_path, monkeypatch):
        module_path, kb_path = self._setup(tmp_path)

        def _fail():
            raise AssertionError("require_repository must not be called with --no-branch --no-commit")

        monkeypatch.setattr("oops.commands.addons.refactor.require_repository", _fail)
        commit_calls = self._patch_commit(monkeypatch)

        result = self._runner().invoke(
            main, [str(module_path), "--kb", str(kb_path), "--no-branch", "--no-commit"]
        )
        assert result.exit_code == 0
        assert len(commit_calls) == 0

    def test_default_one_commit_per_module(self, tmp_path, monkeypatch):
        module_path, kb_path = self._setup(tmp_path)
        self._patch_repo(monkeypatch, tmp_path)
        commit_calls = self._patch_commit(monkeypatch)

        result = self._runner().invoke(main, [str(module_path), "--kb", str(kb_path)])
        assert result.exit_code == 0
        assert len(commit_calls) == 1
        _, kwargs = commit_calls[0]
        assert kwargs["module"] == "my_module"
        assert "description" in kwargs

    def test_per_module_commit_message_format(self):
        from oops.core.messages import commit_messages

        msg = commit_messages.refactor_per_module.format(
            module="my_module",
            description="models/my_model.py\nmodels/other.py",
        )
        assert msg.startswith("refactor(my_module): add sections and docstrings")
        assert "\n\n" in msg
        assert "models/my_model.py\nmodels/other.py" in msg

    def test_branch_failure_disables_commit(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        from git import GitCommandError

        module_path, kb_path = self._setup(tmp_path)
        fake_repo = MagicMock()
        fake_repo.git.checkout.side_effect = GitCommandError("checkout", 128)
        monkeypatch.setattr(
            "oops.commands.addons.refactor.require_repository",
            lambda: (fake_repo, tmp_path),
        )
        commit_calls = self._patch_commit(monkeypatch)

        result = self._runner().invoke(main, [str(module_path), "--kb", str(kb_path)])
        assert result.exit_code == 0
        assert len(commit_calls) == 0
        assert "Could not create branch" in result.output


# ---------------------------------------------------------------------------
# TestRefactorMultiModule — Phase 2: nargs=-1, outer loop, generic branch
# ---------------------------------------------------------------------------


class TestRefactorMultiModule:
    """Tests for multi-module invocation support."""

    def _runner(self) -> CliRunner:
        return CliRunner()

    def _kb(self, tmp_path: Path) -> Path:
        kb_path = tmp_path / "kb.db"
        _make_kb(kb_path)
        return kb_path

    def _make_two_modules(self, root: Path) -> tuple[Path, Path]:
        mod_a = _make_module(root, "mod_a", {"model_a.py": NEW_MODEL_SOURCE})
        mod_b = _make_module(root, "mod_b", {"model_b.py": NEW_MODEL_SOURCE})
        return mod_a, mod_b

    def _patch_repo(self, monkeypatch, tmp_path: Path):
        from unittest.mock import MagicMock

        fake_repo = MagicMock()
        monkeypatch.setattr(
            "oops.commands.addons.refactor.require_repository",
            lambda: (fake_repo, tmp_path),
        )
        return fake_repo

    def _patch_commit(self, monkeypatch) -> list:
        calls: list = []
        monkeypatch.setattr(
            "oops.commands.addons.refactor.commit",
            lambda *a, **kw: calls.append((a, kw)),
        )
        return calls

    def test_two_modules_each_rewritten(self, tmp_path):
        kb_path = self._kb(tmp_path)
        mod_a, mod_b = self._make_two_modules(tmp_path)
        file_a = mod_a / "models" / "model_a.py"
        file_b = mod_b / "models" / "model_b.py"
        original_a, original_b = file_a.read_text(), file_b.read_text()

        result = self._runner().invoke(
            main,
            [str(mod_a), str(mod_b), "--kb", str(kb_path), "--no-branch", "--no-commit"],
        )
        assert result.exit_code == 0
        assert file_a.read_text() != original_a
        assert file_b.read_text() != original_b

    def test_two_modules_use_generic_branch(self, tmp_path, monkeypatch):
        kb_path = self._kb(tmp_path)
        mod_a, mod_b = self._make_two_modules(tmp_path)
        fake_repo = self._patch_repo(monkeypatch, tmp_path)
        self._patch_commit(monkeypatch)

        result = self._runner().invoke(
            main, [str(mod_a), str(mod_b), "--kb", str(kb_path), "--no-commit"]
        )
        assert result.exit_code == 0
        fake_repo.git.checkout.assert_called_once_with("-b", "refactor/doc-multi")

    def test_one_module_uses_specific_branch(self, tmp_path, monkeypatch):
        kb_path = self._kb(tmp_path)
        mod = _make_module(tmp_path, "my_module", {"model.py": NEW_MODEL_SOURCE})
        fake_repo = self._patch_repo(monkeypatch, tmp_path)
        self._patch_commit(monkeypatch)

        result = self._runner().invoke(
            main, [str(mod), "--kb", str(kb_path), "--no-commit"]
        )
        assert result.exit_code == 0
        fake_repo.git.checkout.assert_called_once_with("-b", "refactor/doc-my_module")

    def test_two_modules_one_commit_each(self, tmp_path, monkeypatch):
        kb_path = self._kb(tmp_path)
        mod_a, mod_b = self._make_two_modules(tmp_path)
        self._patch_repo(monkeypatch, tmp_path)
        commit_calls = self._patch_commit(monkeypatch)

        result = self._runner().invoke(
            main, [str(mod_a), str(mod_b), "--kb", str(kb_path)]
        )
        assert result.exit_code == 0
        assert len(commit_calls) == 2
        committed_modules = {kw["module"] for _, kw in commit_calls}
        assert committed_modules == {"mod_a", "mod_b"}

    def test_module_without_models_dir_warns_and_continues(self, tmp_path):
        kb_path = self._kb(tmp_path)
        mod_a = _make_module(tmp_path, "mod_a", {"model_a.py": NEW_MODEL_SOURCE})
        mod_b = tmp_path / "mod_b"
        mod_b.mkdir()
        file_a = mod_a / "models" / "model_a.py"
        original_a = file_a.read_text()

        result = self._runner().invoke(
            main,
            [str(mod_a), str(mod_b), "--kb", str(kb_path), "--no-branch", "--no-commit"],
        )
        assert result.exit_code == 0
        assert "no models" in result.output.lower()
        assert file_a.read_text() != original_a

    def test_module_without_py_files_warns_and_continues(self, tmp_path):
        kb_path = self._kb(tmp_path)
        mod_a = _make_module(tmp_path, "mod_a", {"model_a.py": NEW_MODEL_SOURCE})
        mod_b = tmp_path / "mod_b"
        (mod_b / "models").mkdir(parents=True)
        file_a = mod_a / "models" / "model_a.py"
        original_a = file_a.read_text()

        result = self._runner().invoke(
            main,
            [str(mod_a), str(mod_b), "--kb", str(kb_path), "--no-branch", "--no-commit"],
        )
        assert result.exit_code == 0
        assert "no .py" in result.output.lower()
        assert file_a.read_text() != original_a

    def test_zero_modules_exits_with_usage_error(self):
        result = self._runner().invoke(main, [])
        assert result.exit_code == 2

    def test_symlinked_module_in_multi_aborts_run(self, tmp_path):
        kb_path = self._kb(tmp_path)
        real_module = _make_module(tmp_path, "real_module", {"model.py": NEW_MODEL_SOURCE})
        symlink_module = tmp_path / "symlink_module"
        symlink_module.symlink_to(real_module)
        real_file = real_module / "models" / "model.py"
        original = real_file.read_text()

        result = self._runner().invoke(
            main,
            [str(real_module), str(symlink_module), "--kb", str(kb_path),
             "--no-branch", "--no-commit"],
        )
        assert result.exit_code == 1
        assert "symlink" in result.output.lower()
        assert real_file.read_text() == original


# ---------------------------------------------------------------------------
# TestAnalyseFileFieldRefs — headline bug fix and sibling tests
# ---------------------------------------------------------------------------


class TestAnalyseFileFieldRefs:
    """Verify that field kwarg signals classify methods correctly."""

    def _empty_kb(self, tmp_path: Path) -> Path:
        kb_path = tmp_path / "empty.db"
        _make_kb(kb_path)
        return kb_path

    def _write_and_analyse(self, tmp_path: Path, source: str) -> dict:
        py_file = tmp_path / "m.py"
        py_file.write_text(textwrap.dedent(source))
        with KBReader(self._empty_kb(tmp_path)) as kb:
            [ci] = analyse_file(py_file, kb, {}, "mymodule")
        return {s.name: s for s in ci.symbols if s.kind == "method"}

    def test_compute_method_without_decorator_via_compute_kwarg(self, tmp_path):
        src = """\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                x = fields.Boolean(compute="_compute_x")
                def _compute_x(self):
                    pass
        """
        method_map = self._write_and_analyse(tmp_path, src)
        assert method_map["_compute_x"].section == "COMPUTE METHODS"

    def test_inverse_method_lands_in_compute(self, tmp_path):
        src = """\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                x = fields.Char(inverse="_inverse_x")
                def _inverse_x(self):
                    pass
        """
        method_map = self._write_and_analyse(tmp_path, src)
        assert method_map["_inverse_x"].section == "COMPUTE METHODS"

    def test_search_method_lands_in_compute(self, tmp_path):
        src = """\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                x = fields.Char(search="_search_x")
                def _search_x(self, op, val):
                    pass
        """
        method_map = self._write_and_analyse(tmp_path, src)
        assert method_map["_search_x"].section == "COMPUTE METHODS"

    def test_default_method_lands_in_default_methods(self, tmp_path):
        src = """\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                x = fields.Char(default="_get_default_x")
                def _get_default_x(self):
                    return "foo"
        """
        method_map = self._write_and_analyse(tmp_path, src)
        assert method_map["_get_default_x"].section == "DEFAULT METHODS"

    def test_selection_method_lands_in_selection_methods(self, tmp_path):
        src = """\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                state = fields.Selection(selection="_get_states")
                def _get_states(self):
                    return [("a", "A")]
        """
        method_map = self._write_and_analyse(tmp_path, src)
        assert method_map["_get_states"].section == "SELECTION METHODS"

    def test_unreferenced_compute_like_method_is_helper(self, tmp_path):
        src = """\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                def _compute_nothing(self):
                    pass
        """
        method_map = self._write_and_analyse(tmp_path, src)
        assert method_map["_compute_nothing"].section == "HELPER METHODS"

    def test_rewrite_places_compute_method_under_compute_header(self, tmp_path):
        src = textwrap.dedent("""\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                x = fields.Boolean(compute="_compute_x")
                def _compute_x(self):
                    pass
        """)
        py_file = tmp_path / "m.py"
        py_file.write_text(src)
        with KBReader(self._empty_kb(tmp_path)) as kb:
            classes = analyse_file(py_file, kb, {}, "mymodule")
        new_src = rewrite_file(py_file, classes)
        assert "# === COMPUTE METHODS === #" in new_src
        compute_idx = new_src.index("# === COMPUTE METHODS === #")
        method_idx = new_src.index("def _compute_x")
        assert compute_idx < method_idx
        if "# === HELPER METHODS === #" in new_src:
            assert new_src.index("# === HELPER METHODS === #") > method_idx

    def test_cross_file_compute_via_module_local_refs(self, tmp_path):
        """Field in file A, method in file B — module_local_refs handles the link."""
        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(textwrap.dedent("""\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                x = fields.Boolean(compute="_compute_x")
        """))
        file_b.write_text(textwrap.dedent("""\
            from odoo import fields, models
            class M(models.Model):
                _inherit = 'my.model'
                def _compute_x(self):
                    pass
        """))
        from oops.kb.scanner import build_module_field_refs
        module_local_refs = build_module_field_refs([file_a, file_b])
        with KBReader(self._empty_kb(tmp_path)) as kb:
            [ci] = analyse_file(file_b, kb, {}, "mymodule", module_local_refs)
        method_map = {s.name: s for s in ci.symbols if s.kind == "method"}
        assert method_map["_compute_x"].section == "COMPUTE METHODS"


# ---------------------------------------------------------------------------
# NEW_MODEL_WITH_MIXINS_SOURCE — creator with mixin-only _inherit
# ---------------------------------------------------------------------------

NEW_MODEL_WITH_MIXINS_SOURCE = textwrap.dedent("""\
    from odoo import fields, models


    class ResClient(models.Model):
        _name = 'res.client'
        _inherit = ['mail.thread', 'mail.activity.mixin']

        name = fields.Char()
        stage_id = fields.Many2one('res.client.stage')

        def _relational_fields(self):
            return []
""")


# ---------------------------------------------------------------------------
# TestAnalyseFileCreatorInNonEmptyKB — regression for is_new_model misclassification
# ---------------------------------------------------------------------------


class TestAnalyseFileCreatorInNonEmptyKB:
    """Regression: creator module must not be misclassified when KB contains the model."""

    def _make_client_kb(self, tmp_path: Path) -> Path:
        kb_path = tmp_path / "client.db"
        _make_kb(
            kb_path,
            symbols=[
                _kb_symbol("res.client", "name", "field", module="partner_hub"),
                _kb_symbol("res.client", "_relational_fields", "method", module="partner_hub"),
                _kb_symbol("res.client", "_relational_fields", "method", module="partner_hub_project"),
            ],
            model_origins=[
                {
                    "model": "res.client",
                    "module": "partner_hub",
                    "origin": "local",
                    "role": "create",
                    "model_type": "model",
                    "inherit_json": '["mail.thread", "mail.activity.mixin"]',
                    "inherits_json": "{}",
                    "source_file": "partner_hub/models/res_client.py",
                    "source_line": 12,
                },
                {
                    "model": "res.client",
                    "module": "partner_hub_project",
                    "origin": "local",
                    "role": "extend",
                    "model_type": "model",
                    "inherit_json": "[]",
                    "inherits_json": "{}",
                    "source_file": "partner_hub_project/models/res_client.py",
                    "source_line": 8,
                },
            ],
        )
        return kb_path

    def test_creator_is_new_model_true(self, tmp_path):
        py_file = tmp_path / "res_client.py"
        py_file.write_text(NEW_MODEL_WITH_MIXINS_SOURCE)
        kb_path = self._make_client_kb(tmp_path)
        with KBReader(kb_path) as kb:
            [ci] = analyse_file(py_file, kb, {}, "partner_hub")
        assert ci.is_new_model is True

    def test_extender_is_new_model_false(self, tmp_path):
        src = textwrap.dedent("""\
            from odoo import fields, models
            class ResClient(models.Model):
                _inherit = 'res.client'
                x_extra = fields.Char()
        """)
        py_file = tmp_path / "res_client_ext.py"
        py_file.write_text(src)
        kb_path = self._make_client_kb(tmp_path)
        with KBReader(kb_path) as kb:
            [ci] = analyse_file(py_file, kb, {}, "partner_hub_project")
        assert ci.is_new_model is False

    def test_creator_fields_go_to_base_fields(self, tmp_path):
        py_file = tmp_path / "res_client.py"
        py_file.write_text(NEW_MODEL_WITH_MIXINS_SOURCE)
        kb_path = self._make_client_kb(tmp_path)
        with KBReader(kb_path) as kb:
            [ci] = analyse_file(py_file, kb, {}, "partner_hub")
        field_syms = [s for s in ci.symbols if s.kind == "field"]
        assert field_syms, "expected at least one field"
        assert all(s.section == "BASE FIELDS" for s in field_syms)

    def test_creator_methods_are_not_overrides(self, tmp_path):
        py_file = tmp_path / "res_client.py"
        py_file.write_text(NEW_MODEL_WITH_MIXINS_SOURCE)
        kb_path = self._make_client_kb(tmp_path)
        with KBReader(kb_path) as kb:
            [ci] = analyse_file(py_file, kb, {}, "partner_hub")
        assert all(not s.is_override for s in ci.symbols if s.kind == "method")

    def test_no_model_origins_falls_back_to_new_model_true(self, tmp_path):
        """Module not in model_origins and no other creator → is_new_model=True."""
        py_file = tmp_path / "res_client.py"
        py_file.write_text(NEW_MODEL_WITH_MIXINS_SOURCE)
        kb_path = tmp_path / "bare.db"
        _make_kb(kb_path, symbols=[
            _kb_symbol("res.client", "name", "field", module="partner_hub")
        ])
        with KBReader(kb_path) as kb:
            [ci] = analyse_file(py_file, kb, {}, "partner_hub")
        assert ci.is_new_model is True


# ---------------------------------------------------------------------------
# TestGetInherits / TestGetModelType — scanner helper unit tests
# ---------------------------------------------------------------------------


class TestGetInherits:
    def test_basic_dict(self):
        from oops.kb.scanner import get_inherits
        src = "class Foo(models.Model):\n    _inherits = {'res.partner': 'partner_id'}"
        assert get_inherits(_parse_class(src)) == {"res.partner": "partner_id"}

    def test_empty_when_absent(self):
        from oops.kb.scanner import get_inherits
        assert get_inherits(_parse_class("class Foo(models.Model):\n    pass")) == {}

    def test_multiple_parents(self):
        from oops.kb.scanner import get_inherits
        src = "class Foo(models.Model):\n    _inherits = {'res.partner': 'partner_id', 'res.company': 'company_id'}"
        result = get_inherits(_parse_class(src))
        assert result == {"res.partner": "partner_id", "res.company": "company_id"}

    def test_ignores_non_dict_value(self):
        from oops.kb.scanner import get_inherits
        src = "class Foo(models.Model):\n    _inherits = some_variable"
        assert get_inherits(_parse_class(src)) == {}


class TestGetModelType:
    def test_abstract_model(self):
        from oops.kb.scanner import get_model_type
        assert get_model_type(_parse_class("class Foo(models.AbstractModel): pass")) == "abstract"

    def test_transient_model(self):
        from oops.kb.scanner import get_model_type
        assert get_model_type(_parse_class("class Foo(models.TransientModel): pass")) == "transient"

    def test_concrete_model(self):
        from oops.kb.scanner import get_model_type
        assert get_model_type(_parse_class("class Foo(models.Model): pass")) == "model"

    def test_bare_abstract_name(self):
        from oops.kb.scanner import get_model_type
        assert get_model_type(_parse_class("class Foo(AbstractModel): pass")) == "abstract"

    def test_bare_transient_name(self):
        from oops.kb.scanner import get_model_type
        assert get_model_type(_parse_class("class Foo(TransientModel): pass")) == "transient"
