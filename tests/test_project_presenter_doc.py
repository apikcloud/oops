# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_project_presenter_doc.py — tests/test_project_presenter_doc.py

"""Tests for the shared DocModel pipeline (Stage C): docmodel.py helpers and
ProjectDocPresenter. Consumed by `oops project serve`, `oops mcp`, and the
dashboard — no longer by `oops project doc`, which has been removed."""

from __future__ import annotations

from oops.commands.project.presenters.doc import ProjectDocPresenter
from oops.core.models import Result
from oops.output.base import RenderTarget
from oops.output.docmodel import anchor_for, build_index, group_models_by_bare, resolve_ref


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
        from oops.output.docmodel import method_page_path

        modules = [_module_payload()]
        index = build_index(modules)
        method_id = "pm:project.project#method:_compute_dev_hours"
        ref = resolve_ref(method_id, index)
        assert ref["kind"] == "link"
        assert ref["path"] == method_page_path(method_id)
        assert ref["anchor"] is None  # method pages have no in-page anchor

    def test_field_ref_resolves_to_model_page(self) -> None:
        modules = [_module_payload()]
        index = build_index(modules)
        field_id = "pm:project.project#field:dev_hours"
        ref = resolve_ref(field_id, index)
        assert ref["kind"] == "link"
        assert ref["path"] == "models/project.project.md"
        assert ref["anchor"] == anchor_for(field_id)

    def test_external_ref_is_labeled(self) -> None:
        index = build_index([_module_payload()])
        ref = resolve_ref("res.partner", index, origin="core")
        assert ref == {"kind": "external", "name": "res.partner", "origin": "core"}

    def test_none_ref_returns_none(self) -> None:
        assert resolve_ref(None, {}) is None

    def test_module_nodes_indexed_in_build_index(self) -> None:
        modules = [_module_payload()]
        index = build_index(modules)
        assert "pm" in index, "module technical name should be indexed"
        entry = index["pm"]
        assert entry["type"] == "module"
        assert entry["module"] == "pm"
        assert entry["page"] == "modules/pm.md"
        assert entry["anchor"] is None

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
            "ir": {"metadata": {"schema_version": 3}, "warnings": ["w"],
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

    def test_node_totals_propagated_from_ir(self) -> None:
        result = Result()
        node_totals = {"modules": 1, "models": 2, "fields": 3, "methods": 4, "views": 5, "total": 15}
        result.data = {
            "ir": {"metadata": {"schema_version": 3}, "warnings": [],
                   "modules": [_module_payload()], "node_totals": node_totals},
            "inventory": {},
        }
        out = ProjectDocPresenter().prepare(
            result, target=RenderTarget(audience="machine", verbosity="full")
        )
        dm = out.layout
        assert dm.get("node_totals") == node_totals
