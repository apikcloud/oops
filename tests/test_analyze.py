# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_analyze.py — tests/test_analyze.py

"""Tests for oops/commands/addons/analyze.py."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from oops.commands.addons.analyze import main
from oops.kb.store import write_project_kb

# ---------------------------------------------------------------------------
# KB and module helpers (duplicated from test_refactor.py to avoid cross-file import)
# ---------------------------------------------------------------------------


def _make_kb(
    db_path: Path,
    symbols: list[dict] | None = None,
    modules: dict | None = None,
) -> None:
    scan_results = [{"modules": modules or {}, "symbols": symbols or []}]
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

    def test_explicit_kb(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(module_path)])
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
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(module_path)])
        assert result.exit_code == 0
        assert "NEW" in result.output
        assert "2 fields (base)" in result.output
        assert "2 methods" in result.output

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
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(module_path)])
        assert result.exit_code == 0
        assert "INHERIT" in result.output
        assert "1 new / 1 inherited" in result.output

    def test_text_no_manifest(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "no_manifest",
            manifest=None,
            models={"my_model.py": NEW_MODEL_SOURCE},
        )
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(module_path)])
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
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(module_path)])
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

        result = CliRunner().invoke(main, ["--kb", str(db_path), str(module_path)])
        assert result.exit_code == 0
        assert "model.a" in result.output
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
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(module_path)])
        assert result.exit_code == 0
        assert "2 xml" in result.output
        assert "1 csv" in result.output
        assert "not analysed" in result.output

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
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(module_path)])
        assert result.exit_code == 0
        assert "Static" in result.output
        assert "not analysed" in result.output


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
        result = CliRunner().invoke(
            main, ["--kb", str(db_path), "--format", "json", str(module_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        for key in ("module", "manifest", "models", "structure", "not_analysed", "warnings"):
            assert key in data, f"Missing key: {key}"

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
        result = CliRunner().invoke(
            main, ["--kb", str(db_path), "--format", "json", str(m1), str(m2)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_json_no_warnings_no_text(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(tmp_path, "no_mf", manifest=None)
        result = CliRunner().invoke(
            main, ["--kb", str(db_path), "--format", "json", str(module_path)]
        )
        assert result.exit_code == 0
        # stdout must be valid JSON (no Warning: lines before it)
        data = json.loads(result.output)
        assert len(data["warnings"]) > 0
        # No "Warning:" text mixed into the JSON stream
        assert "Warning:" not in result.output.split("{")[0]

    def test_json_default_serialiser_handles_paths(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
        )
        result = CliRunner().invoke(
            main, ["--kb", str(db_path), "--format", "json", str(module_path)]
        )
        assert result.exit_code == 0
        # If Path objects slipped through, json.dumps would have raised without default=str.
        # The fact that we get valid JSON proves the serializer is working.
        json.loads(result.output)


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

        def fake_build(repo_path, version, modules):  # noqa: ARG001
            build_called.append(True)
            return repo_path / ".oops-cache" / "kb.db"

        with patch("oops.commands.addons.analyze.get_local_repo") as mock_repo, \
                patch("oops.commands.addons.analyze.parse_odoo_version") as mock_ver, \
                patch("oops.commands.addons.analyze.read_installed_modules") as mock_info, \
                patch("oops.commands.addons.analyze.is_project_kb_stale") as mock_stale, \
                patch("oops.commands.addons.analyze.build_project_kb", side_effect=fake_build):
            mock_repo.return_value = (MagicMock(), repo_path)
            mock_ver.return_value = MagicMock(major_version=17)
            mock_info.return_value = MagicMock(modules=["my_module"])
            mock_stale.return_value = (True, "test stale reason")

            result = CliRunner().invoke(main, [str(module_path)])
        assert result.exit_code == 0
        assert build_called

    def test_refresh_forces_rebuild(self, tmp_path: Path) -> None:
        repo_path, module_path = self._make_fake_repo(tmp_path)
        build_called = []

        def fake_build(repo_path, version, modules):  # noqa: ARG001
            build_called.append(True)
            return repo_path / ".oops-cache" / "kb.db"

        with patch("oops.commands.addons.analyze.get_local_repo") as mock_repo, \
                patch("oops.commands.addons.analyze.parse_odoo_version") as mock_ver, \
                patch("oops.commands.addons.analyze.read_installed_modules") as mock_info, \
                patch("oops.commands.addons.analyze.is_project_kb_stale") as mock_stale, \
                patch("oops.commands.addons.analyze.build_project_kb", side_effect=fake_build):
            mock_repo.return_value = (MagicMock(), repo_path)
            mock_ver.return_value = MagicMock(major_version=17)
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
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(m1), str(m2)])
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
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(m1), str(m2)])
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
        result = CliRunner().invoke(main, ["--kb", str(db_path), str(link)])
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
    result = CliRunner().invoke(
        main, ["--kb", str(db_path), "--format", fmt, str(module_path)]
    )
    assert result.exit_code == 0
