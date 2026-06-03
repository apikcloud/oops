# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_analyze.py — tests/test_analyze.py

"""Tests for oops/commands/addons/analyze.py."""

from __future__ import annotations

import json
import textwrap
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from oops.commands.addons.analyze import main
from oops.core.models import Result
from oops.kb.store import write_project_kb
from oops.services.loc import LocStats

# ---------------------------------------------------------------------------
# KB and module helpers (duplicated from test_refactor.py to avoid cross-file import)
# ---------------------------------------------------------------------------


def _make_kb(
    db_path: Path,
    symbols: list[dict] | None = None,
    modules: dict | None = None,
    views: list[dict] | None = None,
    actions: list[dict] | None = None,
    menus: list[dict] | None = None,
    model_origins: list[dict] | None = None,
) -> None:
    scan_results = [
        {
            "modules": modules or {},
            "symbols": symbols or [],
            "views": views or [],
            "actions": actions or [],
            "menus": menus or [],
            "model_origins": model_origins or [],
        }
    ]
    write_project_kb(
        db_path=db_path,
        odoo_version="17.0",
        project="test",
        scope=[],
        sources={"odoo": "/odoo"},
        scan_results=scan_results,
    )


def _kb_model_origin(model: str, module: str, origin: str = "odoo", role: str = "create") -> dict:
    return {
        "model": model,
        "module": module,
        "origin": origin,
        "role": role,
        "model_type": "model",
        "inherit_json": "[]",
        "inherits_json": "{}",
        "source_file": f"addons/{module}/models/{model.replace('.', '_')}.py",
        "source_line": 1,
    }


def _kb_symbol(model: str, name: str, kind: str, module: str = "sale") -> dict:
    return {
        "model": model,
        "name": name,
        "kind": kind,
        "origin": "odoo",
        "module": module,
        "source_file": f"addons/{module}/models/{model.replace('.', '_')}.py",
        "source_line": 10,
        "source_end_line": 15,
    }


def _make_module_full(
    root: Path,
    name: str,
    manifest: dict | None = None,
    models: dict[str, str] | None = None,
    controllers: dict[str, str] | None = None,
    wizard: dict[str, str] | None = None,
    report: dict[str, str] | None = None,
) -> Path:
    module_path = root / name
    module_path.mkdir(parents=True, exist_ok=True)

    if manifest is not None:
        (module_path / "__manifest__.py").write_text(repr(manifest), encoding="utf-8")

    for subdir_name, file_map in [
        ("models", models),
        ("controllers", controllers),
        ("wizard", wizard),
        ("report", report),
    ]:
        if not file_map:
            continue
        subdir = module_path / subdir_name
        subdir.mkdir()
        imports = ", ".join(Path(f).stem for f in file_map if f != "__init__.py")
        if imports:
            (subdir / "__init__.py").write_text(f"from . import {imports}", encoding="utf-8")
        else:
            (subdir / "__init__.py").write_text("", encoding="utf-8")
        for filename, content in file_map.items():
            if filename != "__init__.py":
                (subdir / filename).write_text(content, encoding="utf-8")

    return module_path


NEW_MODEL_SOURCE = textwrap.dedent("""\
    from odoo import fields, models


    class MyModel(models.Model):
        _name = 'my.test.model'

        name = fields.Char(string='Name')
        active = fields.Boolean(default=True)

        def action_open(self):
            pass

        def _compute_state(self):
            pass
""")

INHERIT_MODEL_SOURCE = textwrap.dedent("""\
    from odoo import fields, models


    class ResPartnerExt(models.Model):
        _inherit = 'res.partner'

        x_custom = fields.Char(string='Custom')
        name = fields.Char(string='Name')
""")


# ---------------------------------------------------------------------------
# Helper: mock the infrastructure required by the refactored analyze command
# ---------------------------------------------------------------------------


@contextmanager
def _mock_analyze(tmp_path: Path, db_path: Path):
    """Patch require_repository / require_project / KB detection for unit tests."""
    with patch("oops.commands.addons.analyze.require_repository", return_value=(MagicMock(), tmp_path)), \
            patch("oops.commands.addons.analyze.require_project", return_value=MagicMock(major_version=17.0)), \
            patch("oops.commands.addons.analyze.read_installed_modules", return_value=None), \
            patch("oops.commands.addons.analyze.is_project_kb_stale", return_value=(False, "")), \
            patch("oops.commands.addons.analyze.project_kb_path", return_value=db_path), \
            patch("oops.core.logger.Live", MagicMock()):
        yield


# ---------------------------------------------------------------------------
# TestAnalyzeCLI
# ---------------------------------------------------------------------------


class TestAnalyzeCLI:
    def test_zero_args_exit_2(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(main, [])
        assert result.exit_code == 2

    def test_help_lists_format_flag(self) -> None:
        result = CliRunner().invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--format" in result.output

    def test_no_module_dir(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(main, [str(tmp_path / "nonexistent")])  # noqa: ARG002
        assert result.exit_code == 2

    def test_basic_analysis_works(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "my_module" in result.output


# ---------------------------------------------------------------------------
# TestAnalyzeText
# ---------------------------------------------------------------------------


class TestAnalyzeText:
    def test_text_simple_new_model(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Models (1)" in result.output
        assert "new" in result.output
        assert "2" in result.output

    def test_text_inherit_only(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            symbols=[_kb_symbol("res.partner", "name", "field", "base")],
            modules={"res.partner": {"origin": "odoo", "depends": []}},
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"res_partner_ext.py": INHERIT_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Models (1)" in result.output
        assert "1" in result.output

    def test_text_no_manifest(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "no_manifest",
            manifest=None,
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "<unknown>" in result.output

    def test_text_no_models_dir(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "no_models",
            manifest={"name": "No Models", "depends": ["base"]},
            models=None,
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Models" not in result.output.split("Depends")[1]

    def test_text_strict_imports(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        a_source = textwrap.dedent("""\
            from odoo import fields, models


            class ModelA(models.Model):
                _name = 'model.a'
                name = fields.Char()
        """)
        b_source = textwrap.dedent("""\
            from odoo import fields, models


            class ModelB(models.Model):
                _name = 'model.b'
                name = fields.Char()
        """)
        module_path = tmp_path / "strict_module"
        module_path.mkdir()
        (module_path / "__manifest__.py").write_text(
            repr({"name": "Strict", "depends": ["base"]}), encoding="utf-8"
        )
        models_dir = module_path / "models"
        models_dir.mkdir()
        (models_dir / "__init__.py").write_text("from . import a", encoding="utf-8")
        (models_dir / "a.py").write_text(a_source, encoding="utf-8")
        (models_dir / "b.py").write_text(b_source, encoding="utf-8")

        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Models (1)" in result.output
        assert "model.b" not in result.output

    def test_text_data_files_grouped(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        manifest = {
            "name": "Data Module",
            "depends": ["base"],
            "data": [
                "security/ir.model.access.csv",
                "views/x.xml",
                "views/y.xml",
                "data/z.xml",
            ],
        }
        module_path = _make_module_full(tmp_path, "data_module", manifest=manifest)
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Data" in result.output
        assert "views" in result.output
        assert "xml" in result.output
        assert "csv" in result.output
        assert "✗" in result.output

    def test_text_static_assets_grouped(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        manifest = {
            "name": "Static Module",
            "depends": ["base"],
            "assets": {
                "web.assets_backend": [
                    "my_module/static/src/js/main.js",
                    "my_module/static/src/scss/style.scss",
                ],
                "web.assets_frontend": [
                    "my_module/static/src/js/frontend.js",
                ],
            },
        }
        module_path = _make_module_full(tmp_path, "static_module", manifest=manifest)
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Static" in result.output
        assert "js" in result.output
        assert "✗" in result.output


# ---------------------------------------------------------------------------
# TestAnalyzeJson
# ---------------------------------------------------------------------------


class TestAnalyzeJson:
    def test_json_shape(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "warnings" in data
        assert "modules" in data
        assert isinstance(data["modules"], list)
        module = data["modules"][0]
        for key in ("module", "manifest", "models", "structure", "loc", "views", "not_analysed", "warnings"):
            assert key in module, f"Missing key: {key}"

    def test_json_multi_module_is_list(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        m1 = _make_module_full(
            tmp_path,
            "mod1",
            manifest={"name": "Mod1", "depends": ["base"]},
        )
        m2 = _make_module_full(
            tmp_path,
            "mod2",
            manifest={"name": "Mod2", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(m1), str(m2)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "modules" in data
        assert isinstance(data["modules"], list)
        assert len(data["modules"]) == 2

    def test_json_no_warnings_no_text(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(tmp_path, "no_mf", manifest=None)
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["modules"][0]["warnings"]) > 0
        assert "Warning:" not in result.output.split("{")[0]

    def test_json_includes_loc_block(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        fake_loc = LocStats(python=120, xml=10, javascript=0, docs=5)
        fake_addon = MagicMock()
        fake_addon.path = str(module_path)
        with _mock_analyze(tmp_path, db_path), \
                patch("oops.commands.addons.analyze.get_addon_loc", return_value=fake_loc), \
                patch("oops.commands.addons.analyze.find_addons", return_value=[fake_addon]):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        loc = data["modules"][0]["loc"]
        assert loc["kind"] == "stats"
        assert loc["label"] == "Lines of code"
        vals = {s["name"]: s["value"] for s in loc["values"]}
        assert vals == {
            "python": 120, "xml": 10, "javascript": 0,
            "docs": 5, "total": 135, "pct": "100.0%",
        }

    def test_json_default_serialiser_handles_paths(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        json.loads(result.output)

    def test_json_metrics_shape(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        metrics = data["modules"][0]["metrics"]
        assert metrics["kind"] == "stats"
        assert metrics["label"] == "Metrics"
        assert isinstance(metrics["values"], list)
        stat_names = {s["name"] for s in metrics["values"]}
        assert {"models", "methods"}.issubset(stat_names)
        for s in metrics["values"]:
            assert {"name", "label", "value", "kind", "highlight"} == set(s.keys())

    def test_json_manifest_shape(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        manifest = data["modules"][0]["manifest"]
        assert manifest["kind"] == "stats"
        assert manifest["label"] == "Manifest"
        assert isinstance(manifest["values"], list)
        stat_names = {s["name"] for s in manifest["values"]}
        assert {"name", "version"}.issubset(stat_names)
        for s in manifest["values"]:
            assert {"name", "label", "value", "kind", "highlight"} == set(s.keys())

    def test_json_depends_is_top_level_list(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["modules"][0]["depends"] == ["base"]

    def test_json_metadata_shape(self, tmp_path: Path) -> None:
        from datetime import datetime

        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        meta = data["metadata"]
        assert "command" in meta
        assert "tool_version" in meta
        assert "generated_at" in meta
        assert "git_branch" in meta
        datetime.fromisoformat(meta["generated_at"])
        assert meta["git_branch"] is None or isinstance(meta["git_branch"], str)


# ---------------------------------------------------------------------------
# TestAnalyzeJsonWarnings
# ---------------------------------------------------------------------------


class TestAnalyzeJsonWarnings:
    def test_pre_loop_warnings_in_payload(self, tmp_path: Path) -> None:
        """pre-loop _warn() calls now feed pre_warnings, visible under top-level warnings."""
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with patch("oops.commands.addons.analyze.require_repository") as mock_repo, \
                patch("oops.commands.addons.analyze.require_project", return_value=MagicMock(major_version=17.0)), \
                patch("oops.commands.addons.analyze.read_installed_modules") as mock_info, \
                patch("oops.commands.addons.analyze.is_project_kb_stale") as mock_stale, \
                patch("oops.commands.addons.analyze.compute_root_drift") as mock_drift, \
                patch("oops.commands.addons.analyze.global_kb_path") as mock_gkb, \
                patch("oops.commands.addons.analyze.project_kb_path", return_value=db_path), \
                patch("oops.core.logger.Live", MagicMock()):
            mock_repo.return_value = (MagicMock(), tmp_path)
            mock_info.return_value = type("I", (), {"modules": ["my_module", "ghost_module"]})()
            mock_stale.return_value = (False, "")
            mock_drift.return_value = (["ghost_module"], [])
            mock_gkb.return_value = db_path
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any("ghost_module" in w for w in data["warnings"])

    def test_themes_excluded_from_drift_warning(self, tmp_path: Path) -> None:
        """Theme modules (origin='themes' in the global KB) must be filtered
        out of the list passed to compute_root_drift, on par with origin='odoo'
        and origin='enterprise'.
        """
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            modules={
                "theme_foo": {"origin": "themes", "depends": []},
                "odoo_mod": {"origin": "odoo", "depends": []},
            },
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with patch("oops.commands.addons.analyze.require_repository") as mock_repo, \
                patch("oops.commands.addons.analyze.require_project", return_value=MagicMock(major_version=17.0)), \
                patch("oops.commands.addons.analyze.read_installed_modules") as mock_info, \
                patch("oops.commands.addons.analyze.is_project_kb_stale") as mock_stale, \
                patch("oops.commands.addons.analyze.compute_root_drift") as mock_drift, \
                patch("oops.commands.addons.analyze.global_kb_path") as mock_gkb, \
                patch("oops.commands.addons.analyze.project_kb_path", return_value=db_path), \
                patch("oops.core.logger.Live", MagicMock()):
            mock_repo.return_value = (MagicMock(), tmp_path)
            mock_info.return_value = type(
                "I", (), {"modules": ["my_module", "theme_foo", "odoo_mod"]}
            )()
            mock_stale.return_value = (False, "")
            mock_drift.return_value = ([], [])
            mock_gkb.return_value = db_path
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])

        assert result.exit_code == 0
        assert mock_drift.call_count == 1
        passed_modules = list(mock_drift.call_args.args[1])
        assert "theme_foo" not in passed_modules
        assert "odoo_mod" not in passed_modules
        assert "my_module" in passed_modules

    def test_text_mode_smoke(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "my_module" in result.output
        assert "Done — analysed" in result.output
        assert "My Module" in result.output
        assert "Done —" in result.output


# ---------------------------------------------------------------------------
# TestAnalyzeRebuild
# ---------------------------------------------------------------------------


class TestAnalyzeRebuild:
    def _make_fake_repo(self, tmp_path: Path) -> tuple[Path, Path]:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        db_path = repo_path / ".oops-cache" / "kb.db"
        db_path.parent.mkdir()
        _make_kb(db_path)
        module_path = _make_module_full(
            repo_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        return repo_path, module_path

    def test_rebuild_when_stale(self, tmp_path: Path) -> None:
        repo_path, module_path = self._make_fake_repo(tmp_path)
        build_called = []

        def fake_build(rp, version, modules):  # noqa: ARG001
            build_called.append(True)
            return Result(data=rp / ".oops-cache" / "kb.db")

        with patch("oops.commands.addons.analyze.require_repository") as mock_repo, \
                patch("oops.commands.addons.analyze.require_project", return_value=MagicMock(major_version=17)), \
                patch("oops.commands.addons.analyze.read_installed_modules") as mock_info, \
                patch("oops.commands.addons.analyze.is_project_kb_stale") as mock_stale, \
                patch("oops.commands.addons.analyze.build_project_kb", side_effect=fake_build), \
                patch("oops.core.logger.Live", MagicMock()):
            mock_repo.return_value = (MagicMock(), repo_path)
            mock_info.return_value = MagicMock(modules=["my_module"])
            mock_stale.return_value = (True, "test stale reason")

            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert build_called

    def test_refresh_forces_rebuild(self, tmp_path: Path) -> None:
        repo_path, module_path = self._make_fake_repo(tmp_path)
        build_called = []

        def fake_build(rp, version, modules):  # noqa: ARG001
            build_called.append(True)
            return Result(data=rp / ".oops-cache" / "kb.db")

        with patch("oops.commands.addons.analyze.require_repository") as mock_repo, \
                patch("oops.commands.addons.analyze.require_project", return_value=MagicMock(major_version=17)), \
                patch("oops.commands.addons.analyze.read_installed_modules") as mock_info, \
                patch("oops.commands.addons.analyze.is_project_kb_stale") as mock_stale, \
                patch("oops.commands.addons.analyze.build_project_kb", side_effect=fake_build), \
                patch("oops.core.logger.Live", MagicMock()):
            mock_repo.return_value = (MagicMock(), repo_path)
            mock_info.return_value = MagicMock(modules=["my_module"])
            mock_stale.return_value = (False, "")

            result = CliRunner().invoke(main, ["--refresh", str(module_path)])
        assert result.exit_code == 0
        assert build_called


# ---------------------------------------------------------------------------
# TestAnalyzeMultiModule
# ---------------------------------------------------------------------------


class TestAnalyzeMultiModule:
    def test_two_modules_two_rules(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        m1 = _make_module_full(
            tmp_path, "mod_alpha", manifest={"name": "Alpha", "depends": ["base"]}
        )
        m2 = _make_module_full(
            tmp_path, "mod_beta", manifest={"name": "Beta", "depends": ["base"]}
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(m1), str(m2)])
        assert result.exit_code == 0
        assert "mod_alpha" in result.output
        assert "mod_beta" in result.output

    def test_one_fails_others_continue(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        m1 = _make_module_full(tmp_path, "no_manifest_mod", manifest=None)
        m2 = _make_module_full(
            tmp_path, "good_mod", manifest={"name": "Good", "depends": ["base"]}
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(m1), str(m2)])
        assert result.exit_code == 0
        assert "no_manifest_mod" in result.output
        assert "good_mod" in result.output


# ---------------------------------------------------------------------------
# TestAnalyzeSymlinks
# ---------------------------------------------------------------------------


class TestAnalyzeSymlinks:
    def test_symlinked_module_accepted(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        real_module = _make_module_full(
            tmp_path / "real",
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        link = tmp_path / "my_module"
        link.symlink_to(real_module)
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(link)])
        assert result.exit_code == 0
        assert "my_module" in result.output


# ---------------------------------------------------------------------------
# Regression guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_analyze_exits_cleanly_both_formats(tmp_path: Path, fmt: str) -> None:
    db_path = tmp_path / "kb.db"
    _make_kb(db_path)
    module_path = _make_module_full(
        tmp_path,
        "my_module",
        manifest={"name": "My Module", "depends": ["base"]},
        models={"my_model.py": NEW_MODEL_SOURCE},
    )
    with _mock_analyze(tmp_path, db_path):
        result = CliRunner().invoke(main, ["--format", fmt, str(module_path)])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Fixtures for inherited-methods tests
# ---------------------------------------------------------------------------

INHERIT_MODEL_WITH_SUPER_SOURCE = textwrap.dedent("""\
    from odoo import models


    class ResPartnerExt(models.Model):
        _inherit = 'res.partner'

        def write(self, vals):
            return super().write(vals)
""")

MIXED_OVERRIDE_SUPER_SOURCE = textwrap.dedent("""\
    from odoo import models


    class ResPartnerExt(models.Model):
        _inherit = 'res.partner'

        def name_get(self):
            return []

        def write(self, vals):
            return super().write(vals)
""")

NEW_MODEL_WITH_KB_METHOD_SOURCE = textwrap.dedent("""\
    from odoo import models


    class MyNewModel(models.Model):
        _name = 'my.test.model'

        def write(self, vals):
            return super().write(vals)
""")


# ---------------------------------------------------------------------------
# TestAnalyzeInheritedMethods
# ---------------------------------------------------------------------------


class TestAnalyzeInheritedMethods:
    def test_text_inherited_methods_table_present(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            symbols=[_kb_symbol("res.partner", "write", "method", "base")],
            modules={"res.partner": {"origin": "odoo", "depends": []}},
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"res_partner_ext.py": INHERIT_MODEL_WITH_SUPER_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Inherited methods (1)" in result.output
        assert "write" in result.output

    def test_text_inherited_methods_table_absent_when_zero(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            symbols=[_kb_symbol("res.partner", "name", "field", "base")],
            modules={"res.partner": {"origin": "odoo", "depends": []}},
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"res_partner_ext.py": INHERIT_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Inherited methods (" not in result.output

    def test_json_methods_inherited_keys(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            symbols=[_kb_symbol("res.partner", "write", "method", "base")],
            modules={"res.partner": {"origin": "odoo", "depends": []}},
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"res_partner_ext.py": INHERIT_MODEL_WITH_SUPER_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        methods = data["modules"][0]["models"][0]["methods"]
        assert "inherited" in methods
        assert "inherited_details" in methods
        assert isinstance(methods["inherited"], int)
        assert isinstance(methods["inherited_details"], list)
        assert methods["inherited"] >= 1
        for detail in methods["inherited_details"]:
            assert set(detail.keys()) == {
                "model",
                "method",
                "origin_module",
                "origin",
                "line_start",
                "line_end",
                "source_file",
            }

    def test_json_top_level_symbols_methods_only(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        symbols = data["modules"][0]["symbols"]
        assert symbols, "expected a top-level symbols list"
        names = {s["name"] for s in symbols}
        assert {"action_open", "_compute_state"} <= names
        for s in symbols:
            assert s["kind"] == "method"  # methods only — no fields
            assert {"line_start", "line_end", "source_file"} <= set(s.keys())
            assert s["line_end"] >= s["line_start"] > 0
            assert s["source_file"].startswith("my_module/")
            assert s["source_file"].endswith(".py")

    def test_json_override_details_line_keys(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            symbols=[_kb_symbol("res.partner", "name_get", "method", "base")],
            modules={"res.partner": {"origin": "odoo", "depends": []}},
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"res_partner_ext.py": MIXED_OVERRIDE_SUPER_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        methods = data["modules"][0]["models"][0]["methods"]
        assert methods["overrides"] >= 1
        for detail in methods["override_details"]:
            assert {"line_start", "line_end", "source_file"} <= set(detail.keys())
            assert detail["origin_module"] == "base"
            assert detail["source_file"].endswith(".py")

    def test_stats_panel_field_totals_present(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "Fields (own)" in result.output
        assert "Fields (inherited)" in result.output

    def test_inherited_method_counter_excludes_overrides(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            symbols=[
                _kb_symbol("res.partner", "name_get", "method", "base"),
                _kb_symbol("res.partner", "write", "method", "base"),
            ],
            modules={"res.partner": {"origin": "odoo", "depends": []}},
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"res_partner_ext.py": MIXED_OVERRIDE_SUPER_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        methods = data["modules"][0]["models"][0]["methods"]
        assert methods["overrides"] == 1
        assert methods["inherited"] == 1
        override_names = {d["method"] for d in methods["override_details"]}
        inherited_names = {d["method"] for d in methods["inherited_details"]}
        assert override_names.isdisjoint(inherited_names)

    def test_inherited_method_counter_excludes_new_model_class(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            symbols=[_kb_symbol("my.test.model", "write", "method", "base")],
            modules={"my.test.model": {"origin": "odoo", "depends": []}},
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_new_model.py": NEW_MODEL_WITH_KB_METHOD_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        methods = data["modules"][0]["models"][0]["methods"]
        assert methods["inherited"] == 0
        assert methods["inherited_details"] == []


# ---------------------------------------------------------------------------
# View helpers for new test classes
# ---------------------------------------------------------------------------


def _kb_view(
    xml_id: str,
    module: str,
    mode: str = "primary",
    view_type: str | None = "form",
    inherit_id: str | None = None,
    source_file: str | None = None,
    origin: str = "project",
    fields_json: str = "[]",
    buttons_json: str = "[]",
) -> dict:
    return {
        "xml_id": xml_id,
        "module": module,
        "origin": origin,
        "name": xml_id,
        "model": "my.model",
        "view_type": view_type,
        "inherit_id": inherit_id,
        "mode": mode,
        "source_file": source_file or f"{module}/views/{xml_id.split('.', 1)[-1]}.xml",
        "source_line": 1,
        "source_end_line": 20,
        "fields_json": fields_json,
        "buttons_json": buttons_json,
    }


def _kb_action(xml_id: str, module: str, source_file: str | None = None) -> dict:
    return {
        "xml_id": xml_id,
        "module": module,
        "origin": "project",
        "name": xml_id,
        "source_file": source_file or f"{module}/views/actions.xml",
        "source_line": 1,
    }


def _kb_menu(xml_id: str, module: str, source_file: str | None = None) -> dict:
    return {
        "xml_id": xml_id,
        "module": module,
        "origin": "project",
        "name": xml_id,
        "source_file": source_file or f"{module}/views/menus.xml",
        "source_line": 1,
    }


# ---------------------------------------------------------------------------
# TestAnalyzeViews
# ---------------------------------------------------------------------------


class TestAnalyzeViews:
    def test_views_summary_primary_counts(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            views=[
                _kb_view("my_module.view_form_1", "my_module", mode="primary", view_type="form"),
                _kb_view("my_module.view_form_2", "my_module", mode="primary", view_type="form"),
                _kb_view("my_module.view_list_1", "my_module", mode="primary", view_type="list"),
            ],
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "(primary)" in result.output
        assert "Views (3)" in result.output
        assert "2" in result.output  # form count

    def test_views_summary_extensions(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            views=[
                _kb_view(
                    "my_module.inherit_sale_order_form",
                    "my_module",
                    mode="extension",
                    view_type=None,
                    inherit_id="sale.view_order_form",
                ),
            ],
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "(ext.)" in result.output
        assert "upstream" in result.output
        assert "Views (1)" in result.output

    def test_views_summary_all_zero_no_rows(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "(primary)" not in result.output
        assert "(ext.)" not in result.output

    def test_json_views_block_shape(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            views=[_kb_view("my_module.v1", "my_module", mode="primary", view_type="form")],
            actions=[_kb_action("my_module.act1", "my_module")],
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        views = data["modules"][0]["views"]
        expected_keys = (
            "primary", "extensions", "extensions_by_type",
            "extensions_upstream", "actions", "menus", "unresolved", "list",
        )
        for key in expected_keys:
            assert key in views, f"Missing views key: {key}"
        assert views["actions"] == 1
        assert views["list"], "expected at least one view in the list"
        for v in views["list"]:
            assert {"source_file", "line_start", "line_end"} <= set(v.keys())
            assert v["line_end"] >= v["line_start"]

    def test_json_views_all_zero_still_present(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        views = data["modules"][0]["views"]
        assert views == {
            "primary": {},
            "extensions": 0,
            "extensions_by_type": {},
            "extensions_upstream": 0,
            "actions": 0,
            "menus": 0,
            "unresolved": 0,
            "list": [],
        }


# ---------------------------------------------------------------------------
# TestAnalyzeStructureAnalysed
# ---------------------------------------------------------------------------


class TestAnalyzeStructureAnalysed:
    def test_analysed_cell_flips_green(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            views=[
                _kb_view(
                    "my_module.view_form",
                    "my_module",
                    source_file="my_module/views/form.xml",
                ),
            ],
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={
                "name": "My Module",
                "depends": ["base"],
                "data": ["views/form.xml"],
            },
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "✓" in result.output

    def test_unindexed_xml_stays_red(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={
                "name": "My Module",
                "depends": ["base"],
                "data": ["data/cron.xml"],
            },
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert "✗" in result.output


# ---------------------------------------------------------------------------
# TestAnalyzeAncestorOrigin
# ---------------------------------------------------------------------------


class TestAnalyzeAncestorOrigin:
    def test_json_class_ancestor_fields_present_for_inherit(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            symbols=[_kb_symbol("res.partner", "name", "field", "base")],
            modules={"base": {"origin": "odoo", "depends": []}},
            model_origins=[_kb_model_origin("res.partner", "base", origin="odoo", role="create")],
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"res_partner_ext.py": INHERIT_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        cls = data["modules"][0]["models"][0]
        assert cls["ancestor_model"] == "res.partner"
        assert cls["ancestor_module"] == "base"
        assert cls["ancestor_origin"] == "odoo"

    def test_json_class_ancestor_fields_none_for_new_model(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        cls = data["modules"][0]["models"][0]
        assert cls["ancestor_model"] is None
        assert cls["ancestor_module"] is None
        assert cls["ancestor_origin"] is None

    def test_json_views_list_shape(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            views=[
                _kb_view(
                    "my_module.view_form_1",
                    "my_module",
                    mode="primary",
                    view_type="form",
                    fields_json='["name", "email"]',
                    buttons_json='[{"button_type": "object", "name": "action_confirm"}]',
                ),
            ],
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        view_list = data["modules"][0]["views"]["list"]
        assert len(view_list) == 1
        v = view_list[0]
        for key in ("xml_id", "mode", "view_type", "name", "model", "origin",
                    "inherit_id", "fields_count", "buttons_count",
                    "ancestor_module", "ancestor_origin"):
            assert key in v, f"Missing key: {key}"
        assert v["xml_id"] == "my_module.view_form_1"
        assert v["mode"] == "primary"
        assert v["fields_count"] == 2
        assert v["buttons_count"] == 1
        assert v["ancestor_module"] is None
        assert v["ancestor_origin"] is None

    def test_json_views_list_ancestor_resolved(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(
            db_path,
            views=[
                _kb_view(
                    "sale.view_order_form",
                    "sale",
                    mode="primary",
                    view_type="form",
                    origin="odoo",
                ),
                _kb_view(
                    "my_module.inherit_sale_order_form",
                    "my_module",
                    mode="extension",
                    view_type=None,
                    inherit_id="sale.view_order_form",
                ),
            ],
        )
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["sale"]},
        )
        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        view_list = data["modules"][0]["views"]["list"]
        ext_views = [v for v in view_list if v["mode"] == "extension"]
        assert len(ext_views) == 1
        v = ext_views[0]
        assert v["inherit_id"] == "sale.view_order_form"
        assert v["ancestor_module"] == "sale"
        assert v["ancestor_origin"] == "odoo"
