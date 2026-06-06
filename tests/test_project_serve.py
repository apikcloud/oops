# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_project_serve.py — tests/test_project_serve.py

"""Tests for oops/commands/project/serve.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from oops.commands.project.serve import build_payload, prepare_site_dir
from oops.services.loc import LocStats


def _fake_addon(technical_name: str, path: str) -> MagicMock:
    addon = MagicMock()
    addon.technical_name = technical_name
    addon.path = path
    addon.rel_path = ""
    addon.symlinked = False
    addon.symlink = False
    addon.location = "local"
    addon.submodule = ""
    addon.branch = ""
    addon.pull_request = False
    addon.version = "17.0.1.0.0"
    addon.classification = "custom"
    addon.author = "Apik"
    return addon


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
        addon = _fake_addon("my_module", str(tmp_path / "my_module"))
        with patch("oops.commands.project.doc.list_submodules", return_value={}), \
                patch("oops.commands.project.doc.find_addons", return_value=[addon]), \
                patch("oops.commands.project.doc.enrich_addon"), \
                patch(
                    "oops.commands.project.doc.get_addon_loc",
                    return_value=LocStats(python=10),
                ), \
                patch("oops.commands.project.serve._run_analyze", return_value=_FAKE_IR), \
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

        addon = _fake_addon("my_module", str(tmp_path / "my_module"))
        fake_meta = Metadata(command="project serve", project_name="acme", git_branch="main")
        with patch("oops.commands.project.doc.list_submodules", return_value={}), \
                patch("oops.commands.project.doc.find_addons", return_value=[addon]), \
                patch("oops.commands.project.doc.enrich_addon"), \
                patch(
                    "oops.commands.project.doc.get_addon_loc",
                    return_value=LocStats(python=10),
                ), \
                patch("oops.commands.project.serve._run_analyze", return_value=_FAKE_IR), \
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

        with patch("oops.commands.project.doc.list_submodules", return_value={}), \
                patch("oops.commands.project.doc.find_addons", return_value=[]):
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
        assert (dest / "app.js").exists()

    def test_offline_guard_no_external_urls_in_index_html(self) -> None:
        from oops.core.paths import SPA

        content = (SPA / "index.html").read_text(encoding="utf-8")
        assert "http://" not in content
        assert "https://" not in content

    def test_vendor_files_exist_and_nonempty(self) -> None:
        from oops.core.paths import SPA

        for name in ("alpine.min.js", "fuse.min.js", "d3.min.js"):
            path = Path(str(SPA / "vendor" / name))
            assert path.is_file(), f"missing vendor/{name}"
            assert path.stat().st_size > 1000, f"vendor/{name} suspiciously small"


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
