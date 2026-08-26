# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_project_serve.py — tests/test_project_serve.py

"""Tests for oops/commands/project/serve.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from oops.commands.project.serve import (
    _build_source_roots,
    _read_source_slice,
    _resolve_module_root,
    build_payload,
    merge_source_roots,
    prepare_site_dir,
    source_roots_from_payload,
)


def _fake_inventory(technical_name: str, path: str) -> dict:
    return {
        technical_name: {
            "module": technical_name,
            "path": path,
            "location": "local",
            "symlink": False,
            "submodule": "",
            "branch": "",
            "pr": False,
            "version": "17.0.1.0.0",
            "classification": "custom",
            "author": "Apik",
            "loc": {"python": 10, "xml": 0, "javascript": 0, "docs": 0, "total": 10},
        }
    }


_FAKE_IR = {
    "metadata": {"schema_version": 2},
    "warnings": [],
    "modules": [
        {
            "module": "my_module",
            "manifest": {"name": "My Module"},
            "depends": ["base"],
            "loc": {"total": 10},
            "metrics": {"missing_docs": 0},
            "models": [],
            "fields": [],
            "methods": [],
            "views": [],
        }
    ],
}


class TestBuildPayload:
    def test_build_payload_is_json_clean(self, tmp_path: Path) -> None:
        inventory = _fake_inventory("my_module", str(tmp_path / "my_module"))
        with patch("oops.commands.project.serve.build_inventory", return_value=inventory), \
                patch("oops.commands.project.serve.build_ir", return_value=_FAKE_IR), \
                patch("oops.commands.project.serve.get_metadata", return_value=None):
            payload = build_payload(
                MagicMock(), tmp_path, show_all=False, names=(), refresh=False
            )

        # Must round-trip through JSON without error.
        from oops.output.serializers import to_json_string

        serialized = to_json_string(payload)
        recovered = json.loads(serialized)

        assert set(recovered.keys()) >= {
            "metadata",
            "warnings",
            "modules",
            "models_by_bare",
            "index",
            "schema",
        }

    def test_build_payload_merges_command_metadata(self, tmp_path: Path) -> None:
        from oops.core.metadata import Metadata

        inventory = _fake_inventory("my_module", str(tmp_path / "my_module"))
        fake_meta = Metadata(command="project serve", project_name="acme", git_branch="main")
        with patch("oops.commands.project.serve.build_inventory", return_value=inventory), \
                patch("oops.commands.project.serve.build_ir", return_value=_FAKE_IR), \
                patch("oops.commands.project.serve.get_metadata", return_value=fake_meta):
            payload = build_payload(
                MagicMock(), tmp_path, show_all=False, names=(), refresh=False
            )

        meta = payload["metadata"]
        assert meta["project_name"] == "acme"
        assert meta["git_branch"] == "main"
        assert meta["schema_version"] == 2

    def test_build_payload_empty_inventory_raises_early_exit(
        self, tmp_path: Path
    ) -> None:
        import pytest
        from oops.core.exceptions import EarlyExit

        with patch("oops.commands.project.serve.build_inventory", return_value={}):
            with pytest.raises(EarlyExit):
                build_payload(
                    MagicMock(), tmp_path, show_all=False, names=(), refresh=False
                )


class TestPrepareSiteDir:
    def test_prepare_site_dir_writes_data_js(self, tmp_path: Path) -> None:
        dest = tmp_path / "site"
        dest.mkdir()
        payload = {"metadata": {"schema_version": 2}, "modules": []}

        prepare_site_dir(payload, dest)

        data_js = dest / "data.js"
        assert data_js.exists()
        content = data_js.read_text(encoding="utf-8")
        assert content.startswith("window.OOPS = ")
        assert content.endswith(";\n")

    def test_prepare_site_dir_copies_index_and_app(self, tmp_path: Path) -> None:
        dest = tmp_path / "site"
        dest.mkdir()
        payload = {"metadata": {}}

        prepare_site_dir(payload, dest)

        assert (dest / "index.html").exists()
        assert (dest / "dist" / "app.bundle.js").exists()

    def test_offline_guard_no_external_urls_in_index_html(self) -> None:
        from oops.core.paths import UI

        content = (UI / "index.html").read_text(encoding="utf-8")
        assert "http://" not in content
        assert "https://" not in content

    def test_bundle_exists_and_nonempty(self) -> None:
        from oops.core.paths import UI

        bundle = Path(str(UI / "dist" / "app.bundle.js"))
        assert bundle.is_file(), "dist/app.bundle.js missing"
        assert bundle.stat().st_size > 10_000, "dist/app.bundle.js suspiciously small"

    def test_bundle_has_a_registered_error_view(self) -> None:
        """Regression: `{"metadata": {"command": "error"}}` payloads (emitted by
        `run_oops()` on a subprocess crash and `Api.doc_project()` on any
        exception) must route to a real view, not the "No view registered"
        fallback — the built bundle must be in sync with ui/src/renderer.ts."""
        from oops.core.paths import UI

        bundle = (UI / "dist" / "app.bundle.js").read_text(encoding="utf-8")
        # viewError's own fallback text — only present if the bundle was built
        # after registering it in renderer.ts's VIEWS map.
        assert "Unknown error." in bundle


class TestResolutionContract:
    """Verify the DocModel carries resolved *_ref keys on field and method nodes."""

    def _make_docmodel(self) -> dict:
        from oops.commands.project.presenters.doc import ProjectDocPresenter
        from oops.core.models import Result
        from oops.output.base import RenderTarget

        result = Result()
        result.data = {
            "ir": {
                "metadata": {"schema_version": 2},
                "warnings": [],
                "modules": [
                    {
                        "module": "pm",
                        "models": [
                            {"id": "pm:project.task", "model": "project.task", "status": "new"}
                        ],
                        "fields": [
                            {
                                "id": "pm:project.task#field:partner_id",
                                "name": "partner_id",
                                "model": "pm:project.task",
                                "type": "Many2one",
                                "comodel": "res.partner",
                                "compute": None,
                            }
                        ],
                        "methods": [
                            {
                                "id": "pm:project.task#method:action_open",
                                "name": "action_open",
                                "model": "pm:project.task",
                            }
                        ],
                        "views": [],
                    }
                ],
            },
            "inventory": {"pm": {"classification": "custom", "loc": {"total": 50}}},
        }
        out = ProjectDocPresenter().prepare(
            result, target=RenderTarget(audience="machine", verbosity="full")
        )
        return out.layout

    def test_field_has_comodel_ref(self) -> None:
        dm = self._make_docmodel()
        mod = dm["modules"][0]
        field = mod["fields"][0]
        assert "comodel_ref" in field
        # res.partner is external → kind external
        assert field["comodel_ref"]["kind"] == "external"
        assert field["comodel_ref"]["name"] == "res.partner"

    def test_method_has_model_ref(self) -> None:
        dm = self._make_docmodel()
        mod = dm["modules"][0]
        method = mod["methods"][0]
        assert "model_ref" in method
        # project.task is in-repo → kind link
        assert method["model_ref"]["kind"] == "link"


class TestResolveModuleRoot:
    def test_flat_layout(self, tmp_path: Path) -> None:
        (tmp_path / "my_mod").mkdir()
        assert _resolve_module_root("my_mod", tmp_path) == str(tmp_path)

    def test_nested_layout_one_deep(self, tmp_path: Path) -> None:
        (tmp_path / "sale-workflow" / "sale_order_type").mkdir(parents=True)
        result = _resolve_module_root("sale_order_type", tmp_path)
        assert result == str(tmp_path / "sale-workflow")

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        assert _resolve_module_root("missing_mod", tmp_path) is None


class TestSourceRootsFromPayload:
    def test_empty_payload(self) -> None:
        assert source_roots_from_payload({}) == {}

    def test_extracts_parent_from_inventory_path(self, tmp_path):
        mod_path = tmp_path / "apik-addons" / "apik_account"
        payload = {
            "modules": [
                {"module": "apik_account", "inventory": {"path": str(mod_path)}},
            ]
        }
        roots = source_roots_from_payload(payload)
        assert roots["apik_account"] == str(tmp_path / "apik-addons")

    def test_skips_modules_without_inventory_path(self) -> None:
        payload = {
            "modules": [
                {"module": "apik_account"},
                {"module": "other", "inventory": {}},
            ]
        }
        assert source_roots_from_payload(payload) == {}


class TestBuildSourceRoots:
    def test_returns_empty_when_kb_absent(self, tmp_path: Path) -> None:
        roots = _build_source_roots(tmp_path)
        assert roots == {}

    def test_maps_flat_module_to_tier_root(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        local_root = tmp_path / "local"
        local_root.mkdir()
        (local_root / "my_mod").mkdir()

        oca_root = tmp_path / "oca"
        oca_root.mkdir()
        (oca_root / "other").mkdir()

        fake_modules = {
            "my_mod": {"origin": "local"},
            "other":  {"origin": "oca"},
            "no_src": {"origin": "missing_origin"},
        }
        fake_sources = {"local": str(local_root), "oca": str(oca_root)}

        with patch("oops.commands.project.serve.project_kb_path") as pkp, \
             patch("oops.commands.project.serve.discover_repo_ids", return_value=["test"]), \
             patch("oops.commands.project.serve.KBReader") as KBR:
            pkp.return_value = MagicMock(exists=lambda: True)
            inst = KBR.return_value.__enter__.return_value
            inst.get_modules.return_value = fake_modules
            inst.get_sources.return_value = fake_sources

            roots = _build_source_roots(tmp_path)

        assert roots["my_mod"] == str(local_root)
        assert roots["other"]  == str(oca_root)
        assert "no_src" not in roots

    def test_maps_nested_module_to_repo_subdir(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        oca_root = tmp_path / ".third-party"
        (oca_root / "sale-workflow" / "sale_order_type").mkdir(parents=True)

        fake_modules = {"sale_order_type": {"origin": "third-party"}}
        fake_sources = {"third-party": str(oca_root)}

        with patch("oops.commands.project.serve.project_kb_path") as pkp, \
             patch("oops.commands.project.serve.discover_repo_ids", return_value=["test"]), \
             patch("oops.commands.project.serve.KBReader") as KBR:
            pkp.return_value = MagicMock(exists=lambda: True)
            inst = KBR.return_value.__enter__.return_value
            inst.get_modules.return_value = fake_modules
            inst.get_sources.return_value = fake_sources

            roots = _build_source_roots(tmp_path)

        assert roots["sale_order_type"] == str(oca_root / "sale-workflow")

    def test_two_tier_odoo_both_resolve(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        addons_root = tmp_path / "community" / "addons"
        odoo_addons_root = tmp_path / "community" / "odoo" / "addons"
        (addons_root / "sale" / "models").mkdir(parents=True)
        (odoo_addons_root / "base" / "models").mkdir(parents=True)

        fake_modules = {
            "sale": {"origin": "odoo"},
            "base": {"origin": "odoo_core"},
        }
        fake_sources = {
            "odoo": str(addons_root),
            "odoo_core": str(odoo_addons_root),
        }

        with patch("oops.commands.project.serve.project_kb_path") as pkp, \
             patch("oops.commands.project.serve.discover_repo_ids", return_value=["test"]), \
             patch("oops.commands.project.serve.KBReader") as KBR:
            pkp.return_value = MagicMock(exists=lambda: True)
            inst = KBR.return_value.__enter__.return_value
            inst.get_modules.return_value = fake_modules
            inst.get_sources.return_value = fake_sources

            roots = _build_source_roots(tmp_path)

        assert roots["sale"] == str(addons_root)
        assert roots["base"] == str(odoo_addons_root)


class TestMergeSourceRoots:
    def test_payload_wins_on_collision(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        kb_root = tmp_path / "odoo_addons"
        project_root = tmp_path / "project_addons"
        (kb_root / "sale").mkdir(parents=True)
        (project_root / "sale").mkdir(parents=True)

        fake_modules = {"sale": {"origin": "odoo"}}
        fake_sources = {"odoo": str(kb_root)}

        payload = {
            "modules": [
                {"module": "sale", "inventory": {"path": str(project_root / "sale")}},
            ]
        }

        with patch("oops.commands.project.serve.project_kb_path") as pkp, \
             patch("oops.commands.project.serve.discover_repo_ids", return_value=["test"]), \
             patch("oops.commands.project.serve.KBReader") as KBR:
            pkp.return_value = MagicMock(exists=lambda: True)
            inst = KBR.return_value.__enter__.return_value
            inst.get_modules.return_value = fake_modules
            inst.get_sources.return_value = fake_sources

            roots = merge_source_roots(payload, tmp_path)

        assert roots["sale"] == str(project_root)

    def test_kb_only_module_included(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        odoo_addons = tmp_path / "odoo_addons"
        (odoo_addons / "base").mkdir(parents=True)

        fake_modules = {"base": {"origin": "odoo_core"}}
        fake_sources = {"odoo_core": str(odoo_addons)}

        with patch("oops.commands.project.serve.project_kb_path") as pkp, \
             patch("oops.commands.project.serve.discover_repo_ids", return_value=["test"]), \
             patch("oops.commands.project.serve.KBReader") as KBR:
            pkp.return_value = MagicMock(exists=lambda: True)
            inst = KBR.return_value.__enter__.return_value
            inst.get_modules.return_value = fake_modules
            inst.get_sources.return_value = fake_sources

            roots = merge_source_roots({}, tmp_path)

        assert roots["base"] == str(odoo_addons)


class TestReadSourceSlice:
    def test_missing_file_param_returns_400(self) -> None:
        status, body = _read_source_slice({}, "", 1, -1)
        assert status == 400
        assert "error" in body

    def test_unknown_module_returns_404(self) -> None:
        status, body = _read_source_slice({}, "unknown_mod/file.py", 1, -1)
        assert status == 404
        assert "unknown module" in body["error"]

    def test_path_traversal_returns_403(self, tmp_path: Path) -> None:
        src = tmp_path / "mymod"
        src.mkdir()
        roots = {"mymod": str(src)}
        status, body = _read_source_slice(roots, "mymod/../../../etc/passwd", 1, -1)
        assert status == 403
        assert "traversal" in body["error"]

    def test_missing_file_returns_404(self, tmp_path: Path) -> None:
        src = tmp_path / "mymod"
        src.mkdir()
        roots = {"mymod": str(src)}
        status, _ = _read_source_slice(roots, "mymod/missing.py", 1, -1)
        assert status == 404

    def test_success_line_slice(self, tmp_path: Path) -> None:
        src = tmp_path / "mymod"
        (src / "mymod" / "models").mkdir(parents=True)
        f = src / "mymod" / "models" / "foo.py"
        f.write_text("\n".join(f"line{i}" for i in range(1, 21)), encoding="utf-8")
        roots = {"mymod": str(src)}
        status, body = _read_source_slice(roots, "mymod/models/foo.py", 3, 5)
        assert status == 200
        assert body["code"] == "line3\nline4\nline5"
        assert body["file"] == "mymod/models/foo.py"

    def test_full_file_when_end_zero_or_negative(self, tmp_path: Path) -> None:
        src = tmp_path / "mymod"
        (src / "mymod").mkdir(parents=True)
        f = src / "mymod" / "a.py"
        f.write_text("a\nb\nc", encoding="utf-8")
        roots = {"mymod": str(src)}
        status, body = _read_source_slice(roots, "mymod/a.py", 1, 0)
        assert status == 200
        assert body["code"] == "a\nb\nc"

        status2, body2 = _read_source_slice(roots, "mymod/a.py", 1, -1)
        assert status2 == 200
        assert body2["code"] == "a\nb\nc"

    def test_boundary_detection_decorated_method(self, tmp_path: Path) -> None:
        src = tmp_path / "mymod"
        (src / "mymod").mkdir(parents=True)
        f = src / "mymod" / "models.py"
        src_text = "\n".join([
            "class MyModel:",
            "    @api.multi",
            "    def action_confirm(self):",
            "        return True",
            "",
            "    @api.multi",
            "    def action_cancel(self):",
            "        return False",
        ])
        f.write_text(src_text, encoding="utf-8")
        roots = {"mymod": str(src)}
        # line_start = 2 (decorator), end = 0 (unknown) → boundary detection
        status, body = _read_source_slice(roots, "mymod/models.py", 2, 0)
        assert status == 200
        code = body["code"]
        assert "def action_confirm" in code
        assert "return True" in code
        assert "def action_cancel" not in code
