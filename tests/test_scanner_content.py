# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_scanner_content.py — tests/test_scanner_content.py

"""Tests for the IR v2 content extraction in oops/kb/scanner.py.

Covers extract_field_details (literal vs dynamic, _() unwrap), signature and
decorator reconstruction, and method/class docstring + _description capture.
"""

from __future__ import annotations

import ast

import pytest
from oops.kb.scanner import (
    decorator_call_texts,
    extract_field_details,
    reconstruct_signature,
)


def _field_stmt(src: str) -> ast.Assign:
    """Parse a single field-assignment line into its Assign node."""
    node = ast.parse(src).body[0]
    assert isinstance(node, ast.Assign)
    return node


def _func(src: str) -> ast.FunctionDef:
    node = ast.parse(src).body[0]
    assert isinstance(node, ast.FunctionDef)
    return node


# ---------------------------------------------------------------------------
# extract_field_details — literals
# ---------------------------------------------------------------------------


def test_field_details_basic_char() -> None:
    d = extract_field_details(_field_stmt("name = fields.Char(string='Name', help='The name')"))
    assert d is not None
    assert d["type"] == "Char"
    assert d["label"] == "Name"
    assert d["help"] == "The name"
    assert d["dynamic"] is False


def test_field_details_positional_label() -> None:
    d = extract_field_details(_field_stmt("name = fields.Char('Positional')"))
    assert d["label"] == "Positional"
    assert d["dynamic"] is False


def test_field_details_string_kwarg_overrides_positional() -> None:
    d = extract_field_details(_field_stmt("name = fields.Char('Pos', string='Kw')"))
    assert d["label"] == "Kw"


def test_field_details_translation_wrapper() -> None:
    d = extract_field_details(_field_stmt("name = fields.Char(string=_('Translated'))"))
    assert d["label"] == "Translated"
    assert d["dynamic"] is False


def test_field_details_dynamic_help() -> None:
    d = extract_field_details(_field_stmt("name = fields.Char(help=SOME_VAR)"))
    assert d["help"] is None
    assert d["dynamic"] is True


def test_field_details_booleans() -> None:
    d = extract_field_details(_field_stmt("active = fields.Boolean(required=True, store=False)"))
    assert d["required"] is True
    assert d["store"] is False
    assert d["readonly"] is None  # not set in source


def test_field_details_relational_positional_comodel() -> None:
    d = extract_field_details(_field_stmt("partner_id = fields.Many2one('res.partner')"))
    assert d["type"] == "Many2one"
    assert d["comodel"] == "res.partner"
    assert d["label"] is None  # positional arg is comodel, not label, for relational


def test_field_details_comodel_name_kwarg() -> None:
    src = "line_ids = fields.One2many(comodel_name='sale.line', inverse_name='order_id')"
    d = extract_field_details(_field_stmt(src))
    assert d["comodel"] == "sale.line"
    assert d["inverse_name"] == "order_id"


def test_field_details_compute_related() -> None:
    d = extract_field_details(_field_stmt("total = fields.Float(compute='_compute_total', related='order_id.amount')"))
    assert d["compute"] == "_compute_total"
    assert d["related"] == "order_id.amount"


def test_field_details_default_literal_repr() -> None:
    d = extract_field_details(_field_stmt("state = fields.Char(default='draft')"))
    assert d["default"] == "'draft'"
    assert d["dynamic"] is False


def test_field_details_default_callable_is_dynamic() -> None:
    d = extract_field_details(_field_stmt("when = fields.Date(default=fields.Date.today)"))
    assert d["default"] is None
    assert d["dynamic"] is True


def test_field_details_selection_literal() -> None:
    d = extract_field_details(
        _field_stmt("state = fields.Selection([('draft', 'Draft'), ('done', 'Done')])")
    )
    assert d["selection"] == [["draft", "Draft"], ["done", "Done"]]
    assert d["dynamic"] is False


def test_field_details_selection_dynamic() -> None:
    d = extract_field_details(_field_stmt("state = fields.Selection(SELECTION_CONST)"))
    assert d["selection"] is None
    assert d["dynamic"] is True


def test_field_details_returns_none_for_non_field() -> None:
    assert extract_field_details(_field_stmt("x = compute_something()")) is None
    assert extract_field_details(_field_stmt("_name = 'my.model'")) is None


# ---------------------------------------------------------------------------
# reconstruct_signature
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not hasattr(ast, "unparse"), reason="ast.unparse requires py3.9+")
class TestSignature:
    def test_simple(self) -> None:
        assert reconstruct_signature(_func("def f(self): pass")) == "(self)"

    def test_defaults_and_varargs(self) -> None:
        sig = reconstruct_signature(_func("def f(self, a, b=2, *args, c=None, **kwargs): pass"))
        assert sig == "(self, a, b=2, *args, c=None, **kwargs)"


# ---------------------------------------------------------------------------
# decorator_call_texts
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not hasattr(ast, "unparse"), reason="ast.unparse requires py3.9+")
class TestDecorators:
    def test_api_depends_args_preserved(self) -> None:
        src = "@api.depends('a.b', 'c')\ndef f(self): pass"
        assert decorator_call_texts(_func(src)) == ["api.depends('a.b', 'c')"]

    def test_multiple_decorators(self) -> None:
        src = "@api.model\n@api.depends('x')\ndef f(self): pass"
        assert decorator_call_texts(_func(src)) == ["api.model", "api.depends('x')"]

    def test_no_decorators(self) -> None:
        assert decorator_call_texts(_func("def f(self): pass")) == []


# ---------------------------------------------------------------------------
# docstrings + _description (via ast.get_docstring, exercised through analyse path)
# ---------------------------------------------------------------------------


def test_method_docstring_capture() -> None:
    fn = _func('def f(self):\n    """Do a thing.\n\n    Details.\n    """\n    pass')
    assert ast.get_docstring(fn, clean=True) == "Do a thing.\n\nDetails."


def test_class_docstring_and_description() -> None:
    src = (
        "class M(models.Model):\n"
        "    '''Class doc.'''\n"
        "    _name = 'my.model'\n"
        "    _description = 'My Model'\n"
    )
    node = ast.parse(src).body[0]
    assert isinstance(node, ast.ClassDef)
    assert ast.get_docstring(node, clean=True) == "Class doc."
    # _description literal extraction mirrors analyse_file's walk.
    desc = None
    for stmt in node.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_description" for t in stmt.targets
        ):
            desc = stmt.value.value if isinstance(stmt.value, ast.Constant) else None
    assert desc == "My Model"
