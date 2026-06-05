# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_project_doc.py — tests/test_project_doc.py

"""Tests for oops/commands/project/doc.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.project.doc import _build_inventory, main
from oops.commands.project.presenters.doc import ProjectDocPresenter
from oops.core.models import Result
from oops.output.base import RenderTarget
from oops.output.docmodel import anchor_for, build_index, group_models_by_bare, resolve_ref
from oops.services.loc import LocStats


def _fake_addon(technical_name: str, path: str, rel_path: str = "", **kw) -> MagicMock:
    addon = MagicMock()
    addon.technical_name = technical_name
    addon.path = path
    addon.rel_path = rel_path
    addon.symlinked = kw.get("symlinked", False)
    addon.symlink = kw.get("symlink", False)
    addon.location = kw.get("location", "local")
    addon.submodule = kw.get("submodule", "")
    addon.branch = kw.get("branch", "")
    addon.pull_request = kw.get("pull_request", False)
    addon.version = kw.get("version", "17.0.1.0.0")
    addon.classification = kw.get("classification", "custom")
    addon.author = kw.get("author", "Apik")
    return addon


class TestBuildInventory:
    def test_joins_git_state_and_loc(self, tmp_path: Path) -> None:
        addon = _fake_addon("my_module", str(tmp_path / "my_module"), classification="custom")
        with patch("oops.commands.project.doc.list_submodules", return_value={}), \
                patch("oops.commands.project.doc.find_addons", return_value=[addon]), \
                patch("oops.commands.project.doc.enrich_addon"), \
                patch("oops.commands.project.doc.get_addon_loc",
                      return_value=LocStats(python=100, xml=20, javascript=0, docs=5)):
            inventory = _build_inventory(MagicMock(), tmp_path, show_all=False, names=())

        assert "my_module" in inventory
        row = inventory["my_module"]
        assert row["classification"] == "custom"
        assert row["loc"]["total"] == 125
        assert row["path"] == str(tmp_path / "my_module")

    def test_name_filter_excludes_unmatched(self, tmp_path: Path) -> None:
        a = _fake_addon("a", str(tmp_path / "a"), rel_path=".third-party/repo_a")
        b = _fake_addon("b", str(tmp_path / "b"), rel_path=".third-party/repo_b")
        subs = {
            ".third-party/repo_a": {"name": "OCA/repo_a"},
            ".third-party/repo_b": {"name": "OCA/repo_b"},
        }
        with patch("oops.commands.project.doc.list_submodules", return_value=subs), \
                patch("oops.commands.project.doc.find_addons", return_value=[a, b]), \
                patch("oops.commands.project.doc.enrich_addon"), \
                patch("oops.commands.project.doc.get_addon_loc", return_value=LocStats()):
            inventory = _build_inventory(MagicMock(), tmp_path, show_all=False, names=("OCA/repo_a",))

        assert set(inventory) == {"a"}


class TestDocCommand:
    def test_combined_payload_written(self, tmp_path: Path) -> None:
        out = tmp_path / "docs"
        addon = _fake_addon("my_module", str(tmp_path / "my_module"))
        fake_ir = {
            "metadata": {"schema_version": 2},
            "warnings": ["w1"],
            "modules": [{"module": "my_module", "models": [], "fields": [], "methods": []}],
        }
        with patch("oops.commands.project.doc.require_repository", return_value=(MagicMock(), tmp_path)), \
                patch("oops.commands.project.doc.require_project", return_value=MagicMock()), \
                patch("oops.commands.project.doc.list_submodules", return_value={}), \
                patch("oops.commands.project.doc.find_addons", return_value=[addon]), \
                patch("oops.commands.project.doc.enrich_addon"), \
                patch("oops.commands.project.doc.get_addon_loc", return_value=LocStats(python=10)), \
                patch("oops.commands.project.doc._run_analyze", return_value=fake_ir), \
                patch("oops.core.logger.Live", MagicMock()):
            result = CliRunner().invoke(main, ["-o", str(out)])

        assert result.exit_code == 0, result.output
        assert (out / "index.md").is_file()
        assert (out / "modules" / "my_module.md").is_file()
        index_md = (out / "index.md").read_text()
        assert "my_module" in index_md

    def test_empty_inventory_exits_clean(self, tmp_path: Path) -> None:
        with patch("oops.commands.project.doc.require_repository", return_value=(MagicMock(), tmp_path)), \
                patch("oops.commands.project.doc.require_project", return_value=MagicMock()), \
                patch("oops.commands.project.doc.list_submodules", return_value={}), \
                patch("oops.commands.project.doc.find_addons", return_value=[]), \
                patch("oops.core.logger.Live", MagicMock()):
            result = CliRunner().invoke(main, ["-o", str(tmp_path / "docs")])

        assert result.exit_code == 0
        assert "No addons to document" in result.output


# ---------------------------------------------------------------------------
# DocModel helpers (Stage C) — pure unit tests
# ---------------------------------------------------------------------------


def _module_payload() -> dict:
    """Minimal IR-v2-shaped module: one model with two same-named-coexisting
    fields cannot exist within one module, so same-name coexistence is tested
    across two modules below. Here: one model, one field, one method."""
    return {
        "module": "pm",
        "models": [
            {"id": "pm:project.project", "model": "project.project", "status": "extension"}
        ],
        "fields": [
            {
                "id": "pm:project.project#field:dev_hours",
                "name": "dev_hours",
                "model": "pm:project.project",
                "compute": "pm:project.project#method:_compute_dev_hours",
                "comodel": "res.partner",  # external
            }
        ],
        "methods": [
            {
                "id": "pm:project.project#method:_compute_dev_hours",
                "name": "_compute_dev_hours",
                "model": "pm:project.project",
            }
        ],
        "views": [],
    }


class TestDocModelHelpers:
    def test_anchor_is_unique_per_id(self) -> None:
        a = anchor_for("pm:project.project#field:dev_hours")
        b = anchor_for("crm:project.project#field:dev_hours")
        assert a != b  # same field name, different module → distinct anchors
        assert "field" in a and "dev" in a and "hours" in a

    def test_in_repo_ref_resolves_to_link(self) -> None:
        modules = [_module_payload()]
        index = build_index(modules)
        ref = resolve_ref("pm:project.project#method:_compute_dev_hours", index)
        assert ref["kind"] == "link"
        assert ref["path"] == "models/project.project.md"
        assert ref["anchor"] == anchor_for("pm:project.project#method:_compute_dev_hours")

    def test_external_ref_is_labeled(self) -> None:
        index = build_index([_module_payload()])
        ref = resolve_ref("res.partner", index, origin="core")
        assert ref == {"kind": "external", "name": "res.partner", "origin": "core"}

    def test_none_ref_returns_none(self) -> None:
        assert resolve_ref(None, {}) is None

    def test_same_named_field_coexists_across_modules(self) -> None:
        m1 = _module_payload()
        m2 = {
            "module": "crm",
            "models": [
                {"id": "crm:project.project", "model": "project.project", "status": "extension"}
            ],
            "fields": [
                {
                    "id": "crm:project.project#field:dev_hours",
                    "name": "dev_hours",
                    "model": "crm:project.project",
                }
            ],
            "methods": [],
            "views": [],
        }
        grouped = group_models_by_bare([m1, m2])
        assert set(grouped) == {"project.project"}
        contribs = grouped["project.project"]["contributions"]
        assert {c["module"] for c in contribs} == {"pm", "crm"}
        # both dev_hours fields survive, one per contribution
        names = [(c["module"], f["name"]) for c in contribs for f in c["fields"]]
        assert ("pm", "dev_hours") in names and ("crm", "dev_hours") in names


class TestProjectDocPresenter:
    def test_to_machine_resolves_and_joins(self) -> None:
        result = Result()
        result.data = {
            "ir": {"metadata": {"schema_version": 2}, "warnings": ["w"],
                   "modules": [_module_payload()]},
            "inventory": {"pm": {"classification": "custom", "loc": {"total": 99}}},
        }
        out = ProjectDocPresenter().prepare(
            result, target=RenderTarget(audience="machine", verbosity="full")
        )
        dm = out.layout
        assert dm["warnings"] == ["w"]
        mod = dm["modules"][0]
        assert mod["inventory"]["classification"] == "custom"
        field = mod["fields"][0]
        assert field["compute_ref"]["kind"] == "link"
        assert field["comodel_ref"]["kind"] == "external"
        assert "project.project" in dm["models_by_bare"]


# ---------------------------------------------------------------------------
# Markdown page builders (Phase 3)
# ---------------------------------------------------------------------------


def _docmodel_two_modules() -> dict:
    """DocModel as ProjectDocPresenter would produce it: project.project
    extended by two modules, one inferred-label field, one compute ref."""
    result = Result()
    result.data = {
        "ir": {
            "metadata": {"schema_version": 2, "tool_version": "v0.0.0",
                         "limitations": ["oca folded into third_party"]},
            "warnings": ["global warning"],
            "modules": [
                {
                    "module": "pm",
                    "manifest": {"name": "Project Mgmt", "version": "17.0.1.0.0",
                                 "author": "Apik", "installable": True},
                    "readme": {"present": True, "format": "md", "content": "# Hello"},
                    "depends": ["base", "crm_ext"],
                    "loc": {"python": 100, "total": 100, "pct": 50.0},
                    "metrics": {"missing_docs": 1},
                    "models": [{"id": "pm:project.project", "model": "project.project",
                                "status": "extension", "inherit_origin": "core",
                                "ancestor_model": "project.project"}],
                    "fields": [{
                        "id": "pm:project.project#field:dev_hours", "name": "dev_hours",
                        "model": "pm:project.project", "type": "Float",
                        "label": None, "label_inferred": True, "help": "Hours spent",
                        "required": True, "origin_status": "new",
                        "compute": "pm:project.project#method:_compute_dev_hours",
                        "comodel": None, "overrides": None,
                    }],
                    "methods": [{
                        "id": "pm:project.project#method:_compute_dev_hours",
                        "name": "_compute_dev_hours", "model": "pm:project.project",
                        "signature": "(self)", "section": "COMPUTE",
                        "decorators": ["api.depends('timesheet_ids')"],
                        "docstring": "Sum the hours.",
                    }],
                    "views": [],
                },
                {
                    "module": "crm_ext",
                    "manifest": {"name": "CRM Ext"},
                    "depends": ["base"],
                    "loc": {"total": 20},
                    "metrics": {"missing_docs": 0},
                    "models": [{"id": "crm_ext:project.project", "model": "project.project",
                                "status": "extension", "inherit_origin": "core"}],
                    "fields": [{
                        "id": "crm_ext:project.project#field:dev_hours", "name": "dev_hours",
                        "model": "crm_ext:project.project", "type": "Float",
                        "label": "Dev Hours", "label_inferred": False, "help": None,
                        "origin_status": "extended",
                        "overrides": {"origin_module": "pm", "origin": "custom"},
                    }],
                    "methods": [],
                    "views": [],
                },
            ],
        },
        "inventory": {
            "pm": {"classification": "custom", "location": "active", "loc": {"total": 100}},
            "crm_ext": {"classification": "oca", "location": "inactive", "loc": {"total": 20}},
        },
    }
    out = ProjectDocPresenter().prepare(
        result, target=RenderTarget(audience="machine", verbosity="full")
    )
    return out.layout


class TestMarkdownPages:
    def test_index_lists_modules_and_models(self) -> None:
        from oops.output.markdown.pages import build_index

        md = build_index(_docmodel_two_modules())
        assert "[pm](modules/pm.md)" in md
        assert "[crm_ext](modules/crm_ext.md)" in md
        assert "[project.project](models/project.project.md)" in md
        assert "oca folded into third_party" in md  # limitation surfaced

    def test_module_toc_links_resolve(self) -> None:
        from oops.output.markdown.pages import build_module

        dm = _docmodel_two_modules()
        pm = next(m for m in dm["modules"] if m["module"] == "pm")
        md = build_module(dm, pm)
        # README md embedded, in-repo dep linked, model page linked from modules/.
        assert "# Hello" in md
        assert "[crm_ext](./crm_ext.md)" in md
        assert "[project.project](../models/project.project.md)" in md
        assert "`base`" in md  # external dep stays code, not a link

    def test_model_page_field_humanized_and_attributed(self) -> None:
        from oops.output.markdown.pages import build_model

        dm = _docmodel_two_modules()
        entry = dm["models_by_bare"]["project.project"]
        md = build_model(dm, "project.project", entry)
        # pm's dev_hours has no label but label_inferred → humanized.
        assert "Dev Hours" in md
        # both modules attributed; same-named field coexists.
        assert "pm" in md and "crm_ext" in md
        # extended field carries its override origin.
        assert "custom" in md
        # method rendered with docstring + depends decorator.
        assert "_compute_dev_hours" in md
        assert "Sum the hours." in md
        assert "depends" in md


# ---------------------------------------------------------------------------
# Audit pages + mermaid (Phase 4)
# ---------------------------------------------------------------------------


def _docmodel_with_overrides_and_views() -> dict:
    result = Result()
    result.data = {
        "ir": {
            "metadata": {"schema_version": 2},
            "warnings": [],
            "modules": [{
                "module": "pm",
                "manifest": {"name": "PM"},
                "depends": ["base", "sale"],
                "loc": {"total": 80},
                "metrics": {"missing_docs": 2},
                "models": [{"id": "pm:sale.order", "model": "sale.order", "status": "extension"}],
                "fields": [],
                "methods": [{
                    "id": "pm:sale.order#method:write", "name": "write",
                    "model": "pm:sale.order", "signature": "(self, vals)", "section": "CRUD",
                    "is_override": True,
                    "overrides": {"origin_module": "sale", "origin": "core",
                                  "ancestor_model": "sale.order"},
                    "is_inherited": False, "inherited_from": None, "docstring": None,
                }],
                "views": [{
                    "id": "pm.inherit_sale_form", "xml_id": "pm.inherit_sale_form",
                    "model": "pm:sale.order", "mode": "extension",
                    "inherit_id": "sale.view_order_form", "ancestor_module": "sale",
                    "inherit_origin": "core",
                }],
            }],
        },
        "inventory": {"pm": {"classification": "custom", "loc": {"total": 80}}},
    }
    out = ProjectDocPresenter().prepare(
        result, target=RenderTarget(audience="machine", verbosity="full")
    )
    return out.layout


class TestAuditPages:
    def test_override_map_node_colored_by_origin(self) -> None:
        from oops.output.markdown.mermaid import override_map

        dm = _docmodel_with_overrides_and_views()
        graph = override_map(dm["modules"])
        assert "```mermaid" in graph
        assert "pm: write" in graph
        assert "sale (core)" in graph
        assert "classDef core" in graph
        assert "class origin__sale core;" in graph

    def test_view_graph_emits_inherit_edges(self) -> None:
        from oops.output.markdown.mermaid import view_graph

        dm = _docmodel_with_overrides_and_views()
        graph = view_graph(dm["modules"])
        assert "```mermaid" in graph
        assert "sale.view_order_form" in graph
        assert "pm.inherit_sale_form" in graph

    def test_audit_index_has_per_module_economics(self) -> None:
        from oops.output.markdown.pages import build_audit_index

        md = build_audit_index(_docmodel_with_overrides_and_views())
        assert "Per-module economics" in md
        assert "pm" in md
        assert "custom" in md  # classification table

    def test_empty_graphs_render_placeholder(self) -> None:
        from oops.output.markdown.pages import build_audit_overrides, build_audit_views

        result = Result()
        result.data = {
            "ir": {"metadata": {}, "warnings": [], "modules": [_module_payload()]},
            "inventory": {},
        }
        dm = ProjectDocPresenter().prepare(
            result, target=RenderTarget(audience="machine", verbosity="full")
        ).layout
        assert "No overrides" in build_audit_overrides(dm)
        assert "No view extensions" in build_audit_views(dm)


class TestFullSiteTree:
    def test_render_site_emits_all_pages(self) -> None:
        from oops.output.formatters import MarkdownSiteFormatter
        from oops.output.layout import Output

        dm = _docmodel_with_overrides_and_views()
        files = MarkdownSiteFormatter().render_site(Output(layout=dm))
        assert "index.md" in files
        assert "modules/pm.md" in files
        assert "models/sale.order.md" in files
        assert "audit/index.md" in files
        assert "audit/overrides.md" in files
        assert "audit/views.md" in files


# ---------------------------------------------------------------------------
# Phase 5 — --clean guard + on-disk integration tree
# ---------------------------------------------------------------------------


def _invoke_doc(tmp_path: Path, out: Path, extra_args=None, input_text=None):
    addon = _fake_addon("pm", str(tmp_path / "pm"))
    fake_ir = {
        "metadata": {"schema_version": 2, "limitations": ["oca folded into third_party"]},
        "warnings": ["a warning"],
        "modules": [{
            "module": "pm", "manifest": {"name": "PM"}, "depends": ["base"],
            "loc": {"total": 5}, "metrics": {"missing_docs": 0},
            "models": [{"id": "pm:res.partner", "model": "res.partner", "status": "extension"}],
            "fields": [], "methods": [], "views": [],
        }],
    }
    with patch("oops.commands.project.doc.require_repository", return_value=(MagicMock(), tmp_path)), \
            patch("oops.commands.project.doc.require_project", return_value=MagicMock()), \
            patch("oops.commands.project.doc.list_submodules", return_value={}), \
            patch("oops.commands.project.doc.find_addons", return_value=[addon]), \
            patch("oops.commands.project.doc.enrich_addon"), \
            patch("oops.commands.project.doc.get_addon_loc", return_value=LocStats(python=5)), \
            patch("oops.commands.project.doc._run_analyze", return_value=fake_ir), \
            patch("oops.core.logger.Live", MagicMock()):
        return CliRunner().invoke(main, ["-o", str(out), *(extra_args or [])], input=input_text)


class TestCleanAndIntegration:
    def test_integration_emits_full_tree(self, tmp_path: Path) -> None:
        out = tmp_path / "docs"
        result = _invoke_doc(tmp_path, out)
        assert result.exit_code == 0, result.output
        for rel in ("index.md", "modules/pm.md", "models/res.partner.md",
                    "audit/index.md", "audit/overrides.md", "audit/views.md"):
            assert (out / rel).is_file(), rel
        # limitation surfaced on stderr.
        assert "oca folded into third_party" in result.output

    def test_clean_declined_aborts(self, tmp_path: Path) -> None:
        out = tmp_path / "docs"
        out.mkdir()
        (out / "stale.md").write_text("old", encoding="utf-8")
        result = _invoke_doc(tmp_path, out, extra_args=["--clean"], input_text="n\n")
        assert result.exit_code == 1
        assert (out / "stale.md").exists()  # not wiped

    def test_clean_accepted_wipes(self, tmp_path: Path) -> None:
        out = tmp_path / "docs"
        out.mkdir()
        (out / "stale.md").write_text("old", encoding="utf-8")
        result = _invoke_doc(tmp_path, out, extra_args=["--clean"], input_text="y\n")
        assert result.exit_code == 0, result.output
        assert not (out / "stale.md").exists()  # wiped
        assert (out / "index.md").is_file()
