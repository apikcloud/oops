# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_domain_profile.py — tests/test_domain_profile.py

"""Tests for domain profile computation and KB module-app resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from oops.commands.addons.domain_profile import (
    _classify_model,
    _resolve_new_model_domain,
    compute_domain_profile,
)
from oops.core.config import AnalyzeConfig
from oops.core.models import ClassSummary, ModuleSummary, ViewsSummary
from oops.kb.build import _resolve_module_apps
from oops.kb.domains import DOMAIN_LABELS, domain_label
from oops.kb.store import KBReader, write_project_kb


# ---------------------------------------------------------------------------
# Helpers — minimal KB fixtures
# ---------------------------------------------------------------------------


def _write_kb(
    db_path: Path,
    modules: dict | None = None,
    model_origins: list[dict] | None = None,
    symbols: list[dict] | None = None,
) -> None:
    write_project_kb(
        db_path=db_path,
        odoo_version="17.0",
        project="test",
        scope=[],
        sources={"odoo": "/odoo"},
        scan_results=[
            {
                "modules": modules or {},
                "symbols": symbols or [],
                "field_refs": [],
                "model_origins": model_origins or [],
            }
        ],
    )


def _mod(name: str, depends: list, application: int = 0, app: str | None = None) -> dict:
    return {"origin": "odoo", "depends": depends, "application": application, "app": app}


def _origin(model: str, module: str, role: str = "create", inherits_json: str = "{}") -> dict:
    return {
        "model": model,
        "module": module,
        "origin": "odoo",
        "role": role,
        "model_type": "model",
        "inherit_json": "[]",
        "inherits_json": inherits_json,
        "source_file": f"{module}/models/{model.replace('.', '_')}.py",
        "source_line": 1,
        "description": None,
    }


# ---------------------------------------------------------------------------
# TestResolveModuleApps
# ---------------------------------------------------------------------------


class TestResolveModuleApps:
    def _scan(self, modules: dict) -> dict:
        return {"modules": modules}

    def test_application_module_owns_itself(self):
        scan = self._scan({"sale": _mod("sale", [], application=1)})
        _resolve_module_apps([scan])
        assert scan["modules"]["sale"]["app"] == "sale"

    def test_direct_dependent_gets_app(self):
        scan = self._scan({
            "sale": _mod("sale", [], application=1),
            "sale_management": _mod("sale_management", ["sale"]),
        })
        _resolve_module_apps([scan])
        assert scan["modules"]["sale_management"]["app"] == "sale"

    def test_transitive_dependent_gets_app(self):
        scan = self._scan({
            "sale": _mod("sale", [], application=1),
            "sale_extension": _mod("sale_extension", ["sale_management"]),
            "sale_management": _mod("sale_management", ["sale"]),
        })
        _resolve_module_apps([scan])
        assert scan["modules"]["sale_extension"]["app"] == "sale"

    def test_base_only_module_gets_none(self):
        scan = self._scan({
            "base": _mod("base", []),
            "my_helper": _mod("my_helper", ["base"]),
        })
        _resolve_module_apps([scan])
        assert scan["modules"]["my_helper"]["app"] is None

    def test_closest_app_wins_in_chain(self):
        """Module depends on two apps; closest in BFS wins."""
        scan = self._scan({
            "sale": _mod("sale", [], application=1),
            "account": _mod("account", [], application=1),
            "sale_account": _mod("sale_account", ["sale", "account"]),
        })
        _resolve_module_apps([scan])
        # sale and account are both direct depends — BFS order picks sale first (first in list)
        assert scan["modules"]["sale_account"]["app"] == "sale"

    def test_cross_scan_result_resolution(self):
        """Module in scan B depends on an app in scan A."""
        scan_a = self._scan({"sale": _mod("sale", [], application=1)})
        scan_b = self._scan({"my_module": _mod("my_module", ["sale"])})
        _resolve_module_apps([scan_a, scan_b])
        assert scan_b["modules"]["my_module"]["app"] == "sale"


# ---------------------------------------------------------------------------
# TestKBReaderHelpers
# ---------------------------------------------------------------------------


class TestKBReaderHelpers:
    def test_get_module_app(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(db_path, modules={
            "sale": _mod("sale", [], application=1, app="sale"),
            "sale_management": _mod("sale_management", ["sale"], app="sale"),
        })
        with KBReader(db_path) as kb:
            assert kb.get_module_app("sale") == "sale"
            assert kb.get_module_app("sale_management") == "sale"
            assert kb.get_module_app("nonexistent") is None

    def test_is_application(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(db_path, modules={
            "sale": _mod("sale", [], application=1),
            "sale_management": _mod("sale_management", ["sale"]),
        })
        with KBReader(db_path) as kb:
            assert kb.is_application("sale") is True
            assert kb.is_application("sale_management") is False
            assert kb.is_application("nonexistent") is False

    def test_get_model_inherits(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(db_path, model_origins=[
            _origin("my.model", "my_module", inherits_json='{"sale.order": "sale_id"}'),
        ])
        with KBReader(db_path) as kb:
            parents = kb.get_model_inherits("my.model")
        assert parents == ["sale.order"]

    def test_get_model_inherits_empty(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(db_path, model_origins=[
            _origin("my.model", "my_module"),
        ])
        with KBReader(db_path) as kb:
            assert kb.get_model_inherits("my.model") == []

    def test_get_model_inherits_missing_model(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(db_path)
        with KBReader(db_path) as kb:
            assert kb.get_model_inherits("no.such.model") == []

    def test_modules_have_application_and_app_fields(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(db_path, modules={"sale": _mod("sale", [], application=1, app="sale")})
        with KBReader(db_path) as kb:
            mods = kb.get_modules()
        assert mods["sale"]["application"] is True
        assert mods["sale"]["app"] == "sale"


# ---------------------------------------------------------------------------
# TestDomainLabel
# ---------------------------------------------------------------------------


class TestDomainLabel:
    def test_known_app_has_label(self):
        assert domain_label("sale") == "Sales"
        assert domain_label("account") == "Accounting"
        assert domain_label("stock") == "Inventory"

    def test_unknown_app_title_cases(self):
        assert domain_label("my_custom_module") == "My Custom Module"

    def test_fallback_single_word(self):
        assert domain_label("purchase") == "Purchase"


# ---------------------------------------------------------------------------
# Helpers for compute_domain_profile tests
# ---------------------------------------------------------------------------


def _make_sym(name: str, kind: str, lineno: int = 1, end_lineno: int = 10,
              is_override: bool = False, kb_entry: dict | None = None,
              field_type: str | None = None, field_details: dict | None = None,
              section: str = "BUSINESS METHODS") -> Any:
    """Build a minimal SymbolInfo-like object."""
    sym = MagicMock()
    sym.name = name
    sym.kind = kind
    sym.lineno = lineno
    sym.end_lineno = end_lineno
    sym.is_override = is_override
    sym.kb_entry = kb_entry
    sym.field_type = field_type
    sym.field_details = field_details
    sym.section = section
    return sym


def _make_ci(model_name: str | None, inherit: list[str], is_new: bool,
             symbols: list = None) -> Any:
    """Build a minimal ClassInfo-like object."""
    ci = MagicMock()
    ci.model_name = model_name
    ci.inherit = inherit
    ci.is_new_model = is_new
    ci.class_name = (model_name or (inherit[0] if inherit else "Unknown")).replace(".", "_")
    ci.symbols = symbols or []
    return ci


def _make_cs(is_new: bool = False, fields_base: int = 0, fields_new: int = 0,
             fields_inherited: int = 0) -> ClassSummary:
    return ClassSummary(
        class_name="Test",
        is_new_model=is_new,
        inherit=[],
        fields_total=fields_base + fields_new + fields_inherited,
        fields_base=fields_base,
        fields_new=fields_new,
        fields_inherited=fields_inherited,
        fields_by_type={},
        methods_total=0,
        methods_by_section={},
        overrides=0,
        override_details=[],
        missing_docstrings=0,
    )


def _make_summary(classes, class_infos, views_summary=None, loc=None) -> ModuleSummary:
    from oops.core.models import StructureSummary
    return ModuleSummary(
        module_name="test_module",
        module_path=Path("/tmp/test_module"),
        manifest={},
        classes=classes,
        structure=StructureSummary(
            data={}, demo={}, controllers_py=0, wizard_py=0, report_py=0, static_by_ext={}
        ),
        views_summary=views_summary,
        class_infos=class_infos,
    )


# ---------------------------------------------------------------------------
# TestComputeDomainProfile
# ---------------------------------------------------------------------------


class TestComputeDomainProfile:
    """Tests for compute_domain_profile with a real SQLite KB."""

    _DEFAULT_WEIGHTS = AnalyzeConfig().domain_weights

    def _make_sale_kb(self, tmp_path: Path) -> Path:
        """Create a minimal KB with sale as an application."""
        db_path = tmp_path / "kb.db"
        _write_kb(
            db_path,
            modules={
                "sale": _mod("sale", [], application=1, app="sale"),
                "base": _mod("base", []),
            },
            model_origins=[
                _origin("sale.order", "sale"),
                _origin("res.partner", "base"),
            ],
        )
        return db_path

    def _make_dual_kb(self, tmp_path: Path) -> Path:
        """KB with sale + account as applications."""
        db_path = tmp_path / "kb.db"
        _write_kb(
            db_path,
            modules={
                "sale": _mod("sale", [], application=1, app="sale"),
                "account": _mod("account", [], application=1, app="account"),
                "base": _mod("base", []),
            },
            model_origins=[
                _origin("sale.order", "sale"),
                _origin("account.move", "account"),
                _origin("res.partner", "base"),
            ],
        )
        return db_path

    def test_extending_sale_order_yields_sales_domain(self, tmp_path):
        db_path = self._make_sale_kb(tmp_path)
        kb_entry = {"module": "sale", "origin": "odoo", "source_file": "sale/models/sale_order.py", "source_line": 1}
        sym_override = _make_sym("action_confirm", "method", is_override=True, kb_entry=kb_entry)
        sym_field = _make_sym("my_field", "field", end_lineno=3)

        ci = _make_ci(None, ["sale.order"], is_new=False, symbols=[sym_override, sym_field])
        cs = _make_cs(is_new=False, fields_new=1)

        summary = _make_summary([cs], [ci])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        assert len(profile["domains"]) == 1
        d = profile["domains"][0]
        assert d["domain"] == "sale"
        assert d["label"] == "Sales"
        assert d["indicators"]["models_extended"] == 1
        assert d["indicators"]["methods_override"] == 1
        assert profile["custom_models"] == 0

    def test_new_model_with_inherits_lands_in_sale(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(
            db_path,
            modules={"sale": _mod("sale", [], application=1, app="sale")},
            model_origins=[
                _origin("sale.order", "sale"),
                _origin("my.model", "test_module", inherits_json='{"sale.order": "sale_order_id"}'),
            ],
        )
        ci = _make_ci("my.model", [], is_new=True, symbols=[])
        cs = _make_cs(is_new=True)

        summary = _make_summary([cs], [ci])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        # Should land in Sales via _inherits → sale.order → sale
        assert any(d["domain"] == "sale" for d in profile["domains"])
        assert profile["custom_models"] == 0

    def test_new_model_with_required_m2o_to_account_move(self, tmp_path):
        db_path = self._make_dual_kb(tmp_path)
        m2o_sym = _make_sym(
            "move_id", "field",
            field_details={"type": "Many2one", "comodel": "account.move", "required": True},
        )
        ci = _make_ci("my.invoice.line", [], is_new=True, symbols=[m2o_sym])
        cs = _make_cs(is_new=True, fields_base=1)

        summary = _make_summary([cs], [ci])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        assert any(d["domain"] == "account" for d in profile["domains"])
        assert profile["custom_models"] == 0

    def test_new_model_no_resolvable_link_increments_custom_models(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(db_path, modules={"base": _mod("base", [])})
        ci = _make_ci("my.standalone", [], is_new=True, symbols=[])
        cs = _make_cs(is_new=True)

        summary = _make_summary([cs], [ci])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        assert profile["custom_models"] == 1
        assert profile["domains"] == []

    def test_score_proportional_sums_to_one(self, tmp_path):
        db_path = self._make_dual_kb(tmp_path)
        kb_entry_sale = {"module": "sale", "origin": "odoo", "source_file": "sale/x.py", "source_line": 1}
        kb_entry_acc = {"module": "account", "origin": "odoo", "source_file": "account/x.py", "source_line": 1}
        sym_sale = _make_sym("m1", "method", is_override=True, kb_entry=kb_entry_sale)
        sym_acc = _make_sym("m2", "method", is_override=True, kb_entry=kb_entry_acc)

        ci_sale = _make_ci(None, ["sale.order"], is_new=False, symbols=[sym_sale])
        ci_acc = _make_ci(None, ["account.move"], is_new=False, symbols=[sym_acc])
        cs = _make_cs(is_new=False)

        summary = _make_summary([cs, cs], [ci_sale, ci_acc])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        total_prop = sum(d["score_proportional"] for d in profile["domains"])
        assert abs(total_prop - 1.0) < 1e-6

    def test_dominant_domain_score_relative_is_one(self, tmp_path):
        db_path = self._make_sale_kb(tmp_path)
        sym = _make_sym("action_confirm", "method", is_override=True,
                        kb_entry={"module": "sale", "origin": "odoo", "source_file": "x.py", "source_line": 1})
        ci = _make_ci(None, ["sale.order"], is_new=False, symbols=[sym])
        cs = _make_cs(is_new=False)

        summary = _make_summary([cs], [ci])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        dominant = profile["domains"][0]
        assert dominant["score_relative"] == 1.0

    def test_empty_module_returns_empty_profile(self, tmp_path):
        db_path = tmp_path / "kb.db"
        _write_kb(db_path)
        summary = _make_summary([], [])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        assert profile["domains"] == []
        assert profile["pillars"] == []
        assert profile["custom_models"] == 0

    def test_pillar_module_goes_to_pillars_list(self, tmp_path):
        """Extending a product model goes to pillars, not domains."""
        db_path = tmp_path / "kb.db"
        _write_kb(
            db_path,
            modules={"product": _mod("product", [])},  # pillar, not application
            model_origins=[_origin("product.product", "product")],
        )
        sym = _make_sym("m1", "method", is_override=True,
                        kb_entry={"module": "product", "origin": "odoo", "source_file": "x.py", "source_line": 1})
        ci = _make_ci(None, ["product.product"], is_new=False, symbols=[sym])
        cs = _make_cs(is_new=False)

        summary = _make_summary([cs], [ci])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        assert profile["domains"] == []
        assert len(profile["pillars"]) == 1
        assert profile["pillars"][0]["domain"] == "product"

    def test_noise_model_excluded(self, tmp_path):
        """Extending a 'base' model (excluded technical) is not attributed."""
        db_path = tmp_path / "kb.db"
        _write_kb(
            db_path,
            modules={"base": _mod("base", [])},
            model_origins=[_origin("res.partner", "base")],
        )
        ci = _make_ci(None, ["res.partner"], is_new=False, symbols=[])
        cs = _make_cs(is_new=False)

        summary = _make_summary([cs], [ci])

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        assert profile["domains"] == []
        assert profile["pillars"] == []

    def test_view_attributed_to_correct_domain(self, tmp_path):
        db_path = self._make_sale_kb(tmp_path)
        vs = ViewsSummary(
            primary_by_type={}, extensions=1, extensions_by_type={"form": 1},
            extensions_upstream=1, actions=0, menus=0, unresolved=0,
            view_list=[
                {"model": "sale.order", "mode": "extension", "xml_id": "test.view_1",
                 "view_type": "form", "origin": "apik", "inherit_id": "sale.view_order_form",
                 "ancestor_module": "sale", "ancestor_origin": "odoo",
                 "fields_count": 2, "buttons_count": 0, "name": "Test View",
                 "source_file": "test_module/views/sale.xml", "line_start": 1, "line_end": 10},
            ],
        )
        summary = _make_summary([], [], views_summary=vs)

        with KBReader(db_path) as kb:
            profile = compute_domain_profile(summary, kb, self._DEFAULT_WEIGHTS)

        assert any(d["domain"] == "sale" for d in profile["domains"])
        assert profile["domains"][0]["indicators"]["views_extended"] == 1


# ---------------------------------------------------------------------------
# TestAnalyzeConfig
# ---------------------------------------------------------------------------


class TestAnalyzeConfig:
    def test_defaults_are_set(self):
        cfg = AnalyzeConfig()
        assert cfg.domain_weights["w_model_extend"] == 5.0
        assert cfg.domain_weights["w_loc"] == 1.0

    def test_partial_override_merged_correctly(self):
        from oops.core.config import _apply, Config
        cfg = Config()
        _apply(cfg, {"analyze": {"domain_weights": {"w_loc": 2.0}}})
        # Config._apply replaces the whole dict; consumer should merge with defaults.
        merged = {**AnalyzeConfig().domain_weights, **cfg.analyze.domain_weights}
        assert merged["w_loc"] == 2.0
        assert merged["w_model_extend"] == 5.0  # default preserved via consumer merge
