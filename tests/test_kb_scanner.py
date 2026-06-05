# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_kb_scanner.py — tests/test_kb_scanner.py

"""Tests for oops/kb/scanner.py."""

from __future__ import annotations

import ast
import logging
import textwrap
from pathlib import Path

from oops.kb.scanner import (
    _extract_string_value,
    _parse_file,
    build_module_field_refs,
    classify_method,
    discover_root_addons,
    extract_field_refs,
    get_description,
    odoo_addons_roots,
    scan_module,
    scan_tier,
    tier_root_from_real_path,
)
from oops.kb.scanner import (
    get_model_names as _get_model_names,
)
from oops.kb.scanner import (
    is_field_assignment as _is_field_assignment,
)
from oops.kb.scanner import (
    is_odoo_model_class as _is_odoo_model_class,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_expr(src: str) -> ast.expr:
    return ast.parse(src, mode="eval").body


def _parse_class(src: str) -> ast.ClassDef:
    tree = ast.parse(textwrap.dedent(src))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))


def _parse_stmt(src: str) -> ast.stmt:
    return ast.parse(textwrap.dedent(src)).body[0]


def _make_module(
    parent: Path,
    name: str,
    manifest: str | None = "{'name': 'Test', 'depends': ['base']}",
    models: dict[str, str] | None = None,
    use_openerp: bool = False,
) -> Path:
    """Create a minimal Odoo module directory for testing."""
    module_dir = parent / name
    module_dir.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        fname = "__openerp__.py" if use_openerp else "__manifest__.py"
        (module_dir / fname).write_text(manifest, encoding="utf-8")
    if models:
        models_dir = module_dir / "models"
        models_dir.mkdir(exist_ok=True)
        for filename, content in models.items():
            (models_dir / filename).write_text(textwrap.dedent(content), encoding="utf-8")
    return module_dir


# ---------------------------------------------------------------------------
# Source snippets
# ---------------------------------------------------------------------------

SIMPLE_MODEL = """\
    from odoo import fields, models

    class ResPartner(models.Model):
        _name = 'res.partner'
        name = fields.Char(string='Name')
        email = fields.Char(string='Email')

        def action_open(self):
            pass
"""

INHERIT_MODEL = """\
    from odoo import fields, models

    class SaleOrder(models.Model):
        _inherit = 'sale.order'
        x_custom = fields.Char()

        def write(self, vals):
            return super().write(vals)
"""

ASYNC_METHOD_MODEL = """\
    from odoo import fields, models

    class MyModel(models.Model):
        _name = 'my.model'
        name = fields.Char()

        async def _async_helper(self):
            pass
"""

DESCRIBED_MODEL = """\
    from odoo import fields, models

    class MyModel(models.Model):
        _name = 'my.model'
        _description = 'My Model'
        name = fields.Char()
"""

DYNAMIC_DESCRIPTION_MODEL = """\
    from odoo import fields, models

    class MyModel(models.Model):
        _name = 'my.model'
        _description = _('My Model')
        name = fields.Char()
"""


# ---------------------------------------------------------------------------
# TestParseFile
# ---------------------------------------------------------------------------


class TestParseFile:
    def test_valid_file_returns_module(self, tmp_path):
        f = tmp_path / "model.py"
        f.write_text("x = 1\n")
        result = _parse_file(f)
        assert isinstance(result, ast.Module)

    def test_syntax_error_returns_none(self, tmp_path, caplog):
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n    pass")
        with caplog.at_level(logging.WARNING, logger="oops"):
            result = _parse_file(f)
        assert result is None
        assert any("bad.py" in msg or "Syntax" in msg for msg in caplog.messages)

    def test_missing_file_returns_none(self, tmp_path, caplog):
        with caplog.at_level(logging.WARNING, logger="oops"):
            result = _parse_file(tmp_path / "nonexistent.py")
        assert result is None


# ---------------------------------------------------------------------------
# TestExtractStringValue
# ---------------------------------------------------------------------------


class TestExtractStringValue:
    def test_string_constant(self):
        assert _extract_string_value(_parse_expr("'sale.order'")) == "sale.order"

    def test_non_string_constant_returns_none(self):
        assert _extract_string_value(_parse_expr("42")) is None

    def test_single_element_list(self):
        assert _extract_string_value(_parse_expr("['sale.order']")) == "sale.order"

    def test_multi_element_list_returns_none(self):
        assert _extract_string_value(_parse_expr("['a', 'b']")) is None

    def test_other_node_type_returns_none(self):
        assert _extract_string_value(_parse_expr("foo.bar")) is None


# ---------------------------------------------------------------------------
# TestIsOdooModelClass
# ---------------------------------------------------------------------------


class TestIsOdooModelClass:
    def test_models_model(self):
        assert _is_odoo_model_class(_parse_class("class Foo(models.Model): pass")) is True

    def test_transient_model(self):
        assert _is_odoo_model_class(_parse_class("class Foo(models.TransientModel): pass")) is True

    def test_abstract_model(self):
        assert _is_odoo_model_class(_parse_class("class Foo(models.AbstractModel): pass")) is True

    def test_bare_name_model(self):
        assert _is_odoo_model_class(_parse_class("class Foo(Model): pass")) is True

    def test_plain_object(self):
        assert _is_odoo_model_class(_parse_class("class Foo(object): pass")) is False

    def test_no_bases(self):
        assert _is_odoo_model_class(_parse_class("class Foo: pass")) is False


# ---------------------------------------------------------------------------
# TestGetModelNames
# ---------------------------------------------------------------------------


class TestGetModelNames:
    def test_name_only(self):
        node = _parse_class("class C(models.Model):\n    _name = 'sale.order'")
        assert _get_model_names(node) == ("sale.order", [])

    def test_inherit_string(self):
        node = _parse_class("class C(models.Model):\n    _inherit = 'sale.order'")
        assert _get_model_names(node) == (None, ["sale.order"])

    def test_inherit_list(self):
        node = _parse_class("class C(models.Model):\n    _inherit = ['sale.order', 'mail.thread']")
        name, inherit = _get_model_names(node)
        assert name is None
        assert inherit == ["sale.order", "mail.thread"]

    def test_both_name_and_inherit(self):
        src = "class C(models.Model):\n    _name = 'my.model'\n    _inherit = ['mail.thread']"
        name, inherit = _get_model_names(_parse_class(src))
        assert name == "my.model"
        assert inherit == ["mail.thread"]

    def test_empty_class(self):
        assert _get_model_names(_parse_class("class C(models.Model): pass")) == (None, [])


# ---------------------------------------------------------------------------
# TestIsFieldAssignment
# ---------------------------------------------------------------------------


class TestIsFieldAssignment:
    def test_attribute_style(self):
        stmt = _parse_stmt("partner_id = fields.Many2one('res.partner')")
        result = _is_field_assignment(stmt)
        assert result is not None
        assert result[0] == "partner_id"
        assert result[2] == "Many2one"

    def test_bare_name_field(self):
        stmt = _parse_stmt("name = Char(string='Name')")
        result = _is_field_assignment(stmt)
        assert result is not None
        assert result[0] == "name"
        assert result[2] == "Char"

    def test_field_type_boolean(self):
        stmt = _parse_stmt("active = fields.Boolean()")
        result = _is_field_assignment(stmt)
        assert result is not None
        assert result[2] == "Boolean"

    def test_private_attr_is_not_field(self):
        assert _is_field_assignment(_parse_stmt("_name = 'sale.order'")) is None

    def test_plain_int_assignment_is_not_field(self):
        assert _is_field_assignment(_parse_stmt("x = 1")) is None

    def test_method_def_is_not_field(self):
        assert _is_field_assignment(_parse_stmt("def foo(self): pass")) is None

    def test_lineno_matches_source(self):
        src = textwrap.dedent("""\
            pass
            name = fields.Char()
        """)
        tree = ast.parse(src)
        stmt = tree.body[1]
        result = _is_field_assignment(stmt)
        assert result is not None
        assert result[1] == 2


# ---------------------------------------------------------------------------
# TestScanModule
# ---------------------------------------------------------------------------


class TestScanModule:
    def test_module_registered_with_origin(self, tmp_path):
        module_dir = _make_module(tmp_path, "my_sale")
        result = scan_module(module_dir, origin="apik", tier_root=tmp_path)
        assert "my_sale" in result["modules"]
        assert result["modules"]["my_sale"]["origin"] == "apik"

    def test_manifest_depends_parsed(self, tmp_path):
        module_dir = _make_module(tmp_path, "my_sale", manifest="{'name': 'X', 'depends': ['sale', 'base']}")
        result = scan_module(module_dir, origin="apik", tier_root=tmp_path)
        assert result["modules"]["my_sale"]["depends"] == ["sale", "base"]

    def test_no_manifest_yields_empty_depends(self, tmp_path):
        module_dir = tmp_path / "no_manifest"
        module_dir.mkdir()
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        assert result["modules"]["no_manifest"]["depends"] == []

    def test_no_models_dir_yields_no_symbols(self, tmp_path):
        module_dir = _make_module(tmp_path, "no_models")
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        assert result["symbols"] == []

    def test_fields_extracted_from_model(self, tmp_path):
        module_dir = _make_module(tmp_path, "partner", models={"partner.py": SIMPLE_MODEL})
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        symbols = {(s["name"], s["kind"]) for s in result["symbols"]}
        assert ("name", "field") in symbols
        assert ("email", "field") in symbols

    def test_methods_extracted_from_model(self, tmp_path):
        module_dir = _make_module(tmp_path, "partner", models={"partner.py": SIMPLE_MODEL})
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        method_names = {s["name"] for s in result["symbols"] if s["kind"] == "method"}
        assert "action_open" in method_names

    def test_inherit_model_symbols_use_inherited_name(self, tmp_path):
        module_dir = _make_module(tmp_path, "sale_ext", models={"sale_order.py": INHERIT_MODEL})
        result = scan_module(module_dir, origin="apik", tier_root=tmp_path)
        models_found = {s["model"] for s in result["symbols"]}
        assert "sale.order" in models_found
        assert "SaleOrder" not in models_found

    def test_async_methods_extracted(self, tmp_path):
        module_dir = _make_module(tmp_path, "async_mod", models={"model.py": ASYNC_METHOD_MODEL})
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        method_names = {s["name"] for s in result["symbols"] if s["kind"] == "method"}
        assert "_async_helper" in method_names

    def test_source_file_relative_to_tier_root(self, tmp_path):
        tier_root = tmp_path / "tier"
        tier_root.mkdir()
        module_dir = _make_module(tier_root, "partner", models={"partner.py": SIMPLE_MODEL})
        result = scan_module(module_dir, origin="odoo", tier_root=tier_root)
        source_files = {s["source_file"] for s in result["symbols"]}
        assert all(not sf.startswith("/") or not sf.startswith(str(tier_root)) for sf in source_files)
        # All paths should be relative: they start with module name, not /
        assert all(sf.startswith("partner") for sf in source_files)

    def test_source_end_line_captured(self, tmp_path):
        module_dir = _make_module(tmp_path, "partner", models={"partner.py": SIMPLE_MODEL})
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        assert result["symbols"]
        for s in result["symbols"]:
            assert "source_end_line" in s
            assert s["source_end_line"] >= s["source_line"]

    def test_syntax_error_in_model_file_skipped(self, tmp_path):
        module_dir = _make_module(
            tmp_path,
            "broken",
            models={"broken.py": "def broken(:\n    pass", "good.py": SIMPLE_MODEL},
        )
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        # good.py symbols should still be present
        assert len(result["symbols"]) > 0

    def test_model_origins_carry_description(self, tmp_path):
        module_dir = _make_module(tmp_path, "described", models={"m.py": DESCRIBED_MODEL})
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        origin = next(o for o in result["model_origins"] if o["model"] == "my.model")
        assert origin["description"] == "My Model"

    def test_model_origins_description_none_when_absent(self, tmp_path):
        module_dir = _make_module(tmp_path, "partner", models={"partner.py": SIMPLE_MODEL})
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        origin = next(o for o in result["model_origins"] if o["model"] == "res.partner")
        assert origin["description"] is None


# ---------------------------------------------------------------------------
# TestGetDescription
# ---------------------------------------------------------------------------


class TestGetDescription:
    def test_literal_description(self):
        node = _parse_class(DESCRIBED_MODEL)
        assert get_description(node) == "My Model"

    def test_absent_description_returns_none(self):
        node = _parse_class(SIMPLE_MODEL)
        assert get_description(node) is None

    def test_non_literal_description_returns_none(self):
        node = _parse_class(DYNAMIC_DESCRIPTION_MODEL)
        assert get_description(node) is None


# ---------------------------------------------------------------------------
# TestScanTier
# ---------------------------------------------------------------------------


class TestScanTier:
    def test_nonexistent_root_returns_empty(self, tmp_path):
        result = scan_tier(tmp_path / "missing", origin="odoo")
        assert result.data["modules"] == {}
        assert result.data["symbols"] == []
        assert any("missing" in w or "not found" in w for w in result.warnings)

    def test_scans_all_modules_in_tier(self, tmp_path):
        tier_root = tmp_path / "tier"
        tier_root.mkdir()
        _make_module(tier_root, "mod_a", models={"a.py": SIMPLE_MODEL})
        _make_module(tier_root, "mod_b", models={"b.py": INHERIT_MODEL})
        result = scan_tier(tier_root, origin="odoo")
        assert "mod_a" in result.data["modules"]
        assert "mod_b" in result.data["modules"]

    def test_symbols_merged_across_modules(self, tmp_path):
        tier_root = tmp_path / "tier"
        tier_root.mkdir()
        _make_module(tier_root, "mod_a", models={"a.py": SIMPLE_MODEL})
        _make_module(tier_root, "mod_b", models={"b.py": INHERIT_MODEL})
        result = scan_tier(tier_root, origin="odoo")
        assert len(result.data["symbols"]) > 0
        modules_in_symbols = {s["module"] for s in result.data["symbols"]}
        assert "mod_a" in modules_in_symbols
        assert "mod_b" in modules_in_symbols

    def test_allowed_modules_filter(self, tmp_path):
        tier_root = tmp_path / "tier"
        tier_root.mkdir()
        _make_module(tier_root, "mod_a")
        _make_module(tier_root, "mod_b")
        result = scan_tier(tier_root, origin="odoo", allowed_modules={"mod_a"})
        assert "mod_a" in result.data["modules"]
        assert "mod_b" not in result.data["modules"]

    def test_directory_without_manifest_skipped(self, tmp_path):
        tier_root = tmp_path / "tier"
        tier_root.mkdir()
        _make_module(tier_root, "has_manifest")
        no_manifest_dir = tier_root / "no_manifest"
        no_manifest_dir.mkdir()
        result = scan_tier(tier_root, origin="odoo")
        assert "has_manifest" in result.data["modules"]
        assert "no_manifest" not in result.data["modules"]

    def test_files_in_tier_root_ignored(self, tmp_path):
        tier_root = tmp_path / "tier"
        tier_root.mkdir()
        _make_module(tier_root, "real_mod")
        (tier_root / "stray_file.py").write_text("# stray")
        result = scan_tier(tier_root, origin="odoo")
        assert "stray_file" not in result.data["modules"]
        assert "real_mod" in result.data["modules"]


# ---------------------------------------------------------------------------
# TestOdooAddonsRoots
# ---------------------------------------------------------------------------


class TestOdooAddonsRoots:
    def test_both_roots_present(self, tmp_path):
        (tmp_path / "addons").mkdir()
        (tmp_path / "odoo" / "addons").mkdir(parents=True)
        roots = odoo_addons_roots(tmp_path)
        assert tmp_path / "addons" in roots
        assert tmp_path / "odoo" / "addons" in roots

    def test_only_addons(self, tmp_path):
        (tmp_path / "addons").mkdir()
        roots = odoo_addons_roots(tmp_path)
        assert roots == [tmp_path / "addons"]

    def test_only_odoo_addons(self, tmp_path):
        (tmp_path / "odoo" / "addons").mkdir(parents=True)
        roots = odoo_addons_roots(tmp_path)
        assert roots == [tmp_path / "odoo" / "addons"]

    def test_neither_falls_back_to_odoo_path(self, tmp_path):
        roots = odoo_addons_roots(tmp_path)
        assert roots == [tmp_path]


# ---------------------------------------------------------------------------
# TestTierRootFromRealPath
# ---------------------------------------------------------------------------


class TestTierRootFromRealPath:
    def test_third_party_marker(self):
        real_path = Path("/srv/repo/.third-party/some-repo/sale_order_type")
        result = tier_root_from_real_path("third-party", real_path)
        assert result == Path("/srv/repo/.third-party")

    def test_apik_marker(self):
        real_path = Path("/srv/apik-addons/my-repo/account_apik")
        result = tier_root_from_real_path("apik", real_path)
        assert result == Path("/srv/apik-addons")

    def test_unknown_origin_returns_none(self):
        assert tier_root_from_real_path("odoo", Path("/some/path")) is None

    def test_marker_not_in_path_returns_none(self):
        real_path = Path("/srv/completely/different/sale_order_type")
        assert tier_root_from_real_path("third-party", real_path) is None


# ---------------------------------------------------------------------------
# TestResolveSymlinkTiers
# ---------------------------------------------------------------------------


class TestDiscoverRootAddons:
    def _make_real_module(self, base: Path, tier_dir: str, repo: str, name: str) -> Path:
        """Create a real module path matching a tier marker pattern."""
        real = base / tier_dir / repo / name
        real.mkdir(parents=True)
        (real / "__manifest__.py").write_text("{'name': 'Test', 'depends': []}")
        return real

    def test_third_party_symlink_detected(self, tmp_path):
        real = self._make_real_module(tmp_path, ".third-party", "myrepo", "sale_ext")
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        (repo_path / "sale_ext").symlink_to(real)
        tiers = discover_root_addons(repo_path)
        names = [name for name, _ in tiers["third-party"]]
        assert "sale_ext" in names

    def test_apik_symlink_detected(self, tmp_path):
        real = self._make_real_module(tmp_path, "apik-addons", "myrepo", "account_apik")
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        (repo_path / "account_apik").symlink_to(real)
        tiers = discover_root_addons(repo_path)
        names = [name for name, _ in tiers["apik"]]
        assert "account_apik" in names

    def test_unrecognised_symlink_skipped_with_warning(self, tmp_path, caplog):
        real = tmp_path / "somewhere-else" / "mod"
        real.mkdir(parents=True)
        (real / "__manifest__.py").write_text("{'name': 'X', 'depends': []}")
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        (repo_path / "mod").symlink_to(real)
        with caplog.at_level(logging.WARNING, logger="oops"):
            tiers = discover_root_addons(repo_path)
        assert all(len(v) == 0 for v in tiers.values())
        assert any("mod" in msg or "skip" in msg.lower() for msg in caplog.messages)

    def test_allowed_modules_filters_symlinks(self, tmp_path):
        real_a = self._make_real_module(tmp_path, ".third-party", "r", "mod_a")
        real_b = self._make_real_module(tmp_path, ".third-party", "r", "mod_b")
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        (repo_path / "mod_a").symlink_to(real_a)
        (repo_path / "mod_b").symlink_to(real_b)
        tiers = discover_root_addons(repo_path, allowed_modules={"mod_a"})
        names = [name for name, _ in tiers["third-party"]]
        assert "mod_a" in names
        assert "mod_b" not in names

    def test_duplicate_real_path_counted_once(self, tmp_path):
        real = self._make_real_module(tmp_path, ".third-party", "r", "mod")
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        sub = repo_path / "sub"
        sub.mkdir()
        # Two symlinks pointing to the same real path
        (repo_path / "mod").symlink_to(real)
        (sub / "mod").symlink_to(real)
        tiers = discover_root_addons(repo_path)
        assert len(tiers["third-party"]) == 1

    def test_local_root_dir_with_manifest_detected(self, tmp_path):
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        local = repo_path / "owned_at_root"
        local.mkdir()
        (local / "__manifest__.py").write_text("{'name': 'X', 'depends': []}")
        tiers = discover_root_addons(repo_path)
        names = [name for name, _ in tiers["local"]]
        assert "owned_at_root" in names

    def test_local_root_dir_without_manifest_ignored(self, tmp_path):
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        (repo_path / "scripts").mkdir()  # no manifest
        tiers = discover_root_addons(repo_path)
        assert tiers["local"] == []

    def test_local_tier_respects_allowed_modules(self, tmp_path):
        repo_path = tmp_path / "project"
        repo_path.mkdir()
        for name in ("keep", "drop"):
            d = repo_path / name
            d.mkdir()
            (d / "__manifest__.py").write_text("{'name': 'x', 'depends': []}")
        tiers = discover_root_addons(repo_path, allowed_modules={"keep"})
        names = [name for name, _ in tiers["local"]]
        assert names == ["keep"]

    def test_nested_real_dir_under_apik_addons_not_local(self, tmp_path):
        # A real dir under apik-addons/ should NOT show up as 'local'.
        apik = tmp_path / "project" / "apik-addons" / "owner"
        apik.mkdir(parents=True)
        inner = apik / "owned_module"
        inner.mkdir()
        (inner / "__manifest__.py").write_text("{'name': 'X', 'depends': []}")
        repo_path = tmp_path / "project"
        tiers = discover_root_addons(repo_path)
        assert all(name != "owned_module" for name, _ in tiers["local"])


# ---------------------------------------------------------------------------
# TestExtractFieldRefs
# ---------------------------------------------------------------------------


def _parse_assign(src: str) -> ast.Assign:
    tree = ast.parse(textwrap.dedent(src))
    return tree.body[0]  # type: ignore[return-value]


class TestExtractFieldRefs:
    def test_compute_kwarg(self):
        stmt = _parse_assign("x = fields.Boolean(compute='_compute_x')")
        assert extract_field_refs(stmt) == {"compute": "_compute_x"}

    def test_compute_and_inverse(self):
        stmt = _parse_assign("x = fields.Char(compute='_compute_x', inverse='_inverse_x')")
        refs = extract_field_refs(stmt)
        assert refs == {"compute": "_compute_x", "inverse": "_inverse_x"}

    def test_default_kwarg(self):
        stmt = _parse_assign("x = fields.Char(default='_get_default')")
        assert extract_field_refs(stmt) == {"default": "_get_default"}

    def test_selection_kwarg(self):
        stmt = _parse_assign("state = fields.Selection(selection='_get_states')")
        assert extract_field_refs(stmt) == {"selection": "_get_states"}

    def test_lambda_default_ignored(self):
        stmt = _parse_assign("x = fields.Integer(default=lambda self: 0)")
        assert extract_field_refs(stmt) == {}

    def test_bare_callable_ignored(self):
        # Bare callable (no quotes) — not supported per plan
        stmt = _parse_assign("x = fields.Boolean(compute=_compute_x)")
        assert extract_field_refs(stmt) == {}

    def test_non_field_call_returns_empty(self):
        stmt = _parse_assign("x = some_func(compute='_compute_x')")
        refs = extract_field_refs(stmt)
        # Works on any ast.Assign with a Call value — kwarg is in FIELD_REF_KWARGS
        assert refs == {"compute": "_compute_x"}

    def test_no_relevant_kwargs(self):
        stmt = _parse_assign("x = fields.Char(string='Name', required=True)")
        assert extract_field_refs(stmt) == {}


# ---------------------------------------------------------------------------
# TestClassifyMethod
# ---------------------------------------------------------------------------


class TestClassifyMethod:
    def test_crud_create(self):
        assert classify_method("create", []) == "CRUD METHODS"

    def test_crud_write(self):
        assert classify_method("write", []) == "CRUD METHODS"

    def test_crud_unlink(self):
        assert classify_method("unlink", []) == "CRUD METHODS"

    def test_crud_copy(self):
        assert classify_method("copy", []) == "CRUD METHODS"

    def test_default_get_by_name(self):
        assert classify_method("default_get", []) == "DEFAULT METHODS"

    def test_compute_via_api_depends(self):
        assert classify_method("_compute_amount", ["api.depends"]) == "COMPUTE METHODS"

    def test_compute_via_bare_depends(self):
        assert classify_method("_compute_partner", ["depends"]) == "COMPUTE METHODS"

    def test_onchange_decorator(self):
        assert classify_method("_onchange_partner", ["api.onchange"]) == "ONCHANGE METHODS"

    def test_constrains_decorator(self):
        assert classify_method("_check_value", ["constrains"]) == "CONSTRAINT METHODS"

    def test_compute_via_field_ref(self):
        assert classify_method("_compute_x", [], ["compute"]) == "COMPUTE METHODS"

    def test_inverse_via_field_ref(self):
        assert classify_method("_inverse_x", [], ["inverse"]) == "COMPUTE METHODS"

    def test_search_via_field_ref(self):
        assert classify_method("_search_x", [], ["search"]) == "COMPUTE METHODS"

    def test_default_via_field_ref(self):
        assert classify_method("_get_default", [], ["default"]) == "DEFAULT METHODS"

    def test_selection_via_field_ref(self):
        assert classify_method("_get_states", [], ["selection"]) == "SELECTION METHODS"

    def test_decorator_wins_over_field_ref(self):
        # @api.depends takes priority over a hypothetical default= ref
        assert classify_method("_x", ["api.depends"], ["default"]) == "COMPUTE METHODS"

    def test_action_prefix(self):
        assert classify_method("action_confirm", []) == "ACTION METHODS"

    def test_button_prefix(self):
        assert classify_method("button_confirm", []) == "ACTION METHODS"

    def test_underscore_prefix_is_helper(self):
        assert classify_method("_validate", []) == "HELPER METHODS"

    def test_public_method_is_business(self):
        assert classify_method("confirm", []) == "BUSINESS METHODS"

    def test_api_model_is_not_a_classification_signal(self):
        assert classify_method("some_method", ["api.model"], []) == "BUSINESS METHODS"

    def test_crud_wins_over_decorator(self):
        assert classify_method("write", ["api.model"]) == "CRUD METHODS"


# ---------------------------------------------------------------------------
# TestBuildModuleFieldRefs
# ---------------------------------------------------------------------------


class TestBuildModuleFieldRefs:
    def test_single_file_compute(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text(
            textwrap.dedent("""\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                x = fields.Boolean(compute='_compute_x')
        """)
        )
        refs = build_module_field_refs([f])
        assert refs.get(("my.model", "_compute_x")) == ["compute"]

    def test_cross_file(self, tmp_path):
        fa = tmp_path / "a.py"
        fb = tmp_path / "b.py"
        fa.write_text(
            textwrap.dedent("""\
            from odoo import fields, models
            class M(models.Model):
                _name = 'my.model'
                x = fields.Boolean(compute='_compute_x')
        """)
        )
        fb.write_text(
            textwrap.dedent("""\
            from odoo import fields, models
            class M(models.Model):
                _inherit = 'my.model'
                def _compute_x(self): pass
        """)
        )
        refs = build_module_field_refs([fa, fb])
        assert ("my.model", "_compute_x") in refs
        assert "compute" in refs[("my.model", "_compute_x")]

    def test_syntax_error_file_skipped(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n    pass")
        refs = build_module_field_refs([f])
        assert refs == {}

    def test_empty_list(self):
        assert build_module_field_refs([]) == {}


# ---------------------------------------------------------------------------
# Extended TestScanModule — field_type, section, field_refs
# ---------------------------------------------------------------------------

COMPUTE_MODEL = """\
    from odoo import fields, models

    class MyModel(models.Model):
        _name = 'my.model'
        active = fields.Boolean(compute='_compute_active')

        def _compute_active(self):
            pass
"""


class TestScanModuleFieldTypesAndRefs:
    def test_field_type_captured(self, tmp_path):
        module_dir = _make_module(tmp_path, "mod", models={"m.py": COMPUTE_MODEL})
        result = scan_module(module_dir, origin="apik", tier_root=tmp_path)
        field_syms = [s for s in result["symbols"] if s["kind"] == "field"]
        assert len(field_syms) == 1
        assert field_syms[0]["field_type"] == "Boolean"

    def test_method_section_classified_via_field_ref(self, tmp_path):
        module_dir = _make_module(tmp_path, "mod", models={"m.py": COMPUTE_MODEL})
        result = scan_module(module_dir, origin="apik", tier_root=tmp_path)
        method_syms = {s["name"]: s for s in result["symbols"] if s["kind"] == "method"}
        assert method_syms["_compute_active"]["section"] == "COMPUTE METHODS"

    def test_field_refs_emitted(self, tmp_path):
        module_dir = _make_module(tmp_path, "mod", models={"m.py": COMPUTE_MODEL})
        result = scan_module(module_dir, origin="apik", tier_root=tmp_path)
        refs = result["field_refs"]
        assert len(refs) == 1
        assert refs[0]["kwarg"] == "compute"
        assert refs[0]["target_method"] == "_compute_active"

    def test_field_type_is_none_for_methods(self, tmp_path):
        module_dir = _make_module(tmp_path, "mod", models={"m.py": COMPUTE_MODEL})
        result = scan_module(module_dir, origin="apik", tier_root=tmp_path)
        method_syms = [s for s in result["symbols"] if s["kind"] == "method"]
        assert all(s["field_type"] is None for s in method_syms)

    def test_scan_result_has_field_refs_key(self, tmp_path):
        module_dir = _make_module(tmp_path, "mod", models={"m.py": SIMPLE_MODEL})
        result = scan_module(module_dir, origin="odoo", tier_root=tmp_path)
        assert "field_refs" in result

    def test_scan_tier_merges_field_refs(self, tmp_path):
        tier_root = tmp_path / "tier"
        tier_root.mkdir()
        _make_module(tier_root, "mod", models={"m.py": COMPUTE_MODEL})
        result = scan_tier(tier_root, origin="apik")
        assert "field_refs" in result.data
        assert len(result.data["field_refs"]) > 0
