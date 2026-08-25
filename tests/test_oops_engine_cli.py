# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_oops_engine_cli.py — tests/test_oops_engine_cli.py

"""Tests for oops_engine/cli.py — the standalone oops-engine-scan entry point."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oops_engine.cli import main
from oops_engine.store import KBReader


def _make_fixture_addon(root: Path, name: str = "my_module") -> Path:
    mod = root / name
    models_dir = mod / "models"
    models_dir.mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        "{'name': 'My Module', 'version': '17.0.1.0.0', 'depends': ['base']}",
        encoding="utf-8",
    )
    (mod / "__init__.py").write_text("from . import models\n", encoding="utf-8")
    (models_dir / "__init__.py").write_text("from . import res_partner\n", encoding="utf-8")
    (models_dir / "res_partner.py").write_text(
        "from odoo import fields, models\n\n\n"
        "class ResPartner(models.Model):\n"
        "    _inherit = 'res.partner'\n\n"
        "    x_custom_field = fields.Char(string='Custom')\n",
        encoding="utf-8",
    )
    return mod


class TestOopsEngineScanCli:
    def test_sqlite_scan_writes_queryable_kb(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_fixture_addon(workspace)
        db_path = tmp_path / "test.db"

        result = CliRunner().invoke(
            main,
            [
                str(workspace),
                "--repo-id", "test-repo",
                "--odoo-version", "17.0",
                "--backend", "sqlite",
                "--sqlite-path", str(db_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "repo_id='test-repo'" in result.output
        assert db_path.exists()

        with KBReader(db_path, repo_ids=["test-repo"]) as kb:
            modules = kb.get_modules()
            assert "my_module" in modules
            assert modules["my_module"]["origin"] == "test-repo"
            symbols = kb.get_symbol("res.partner", "x_custom_field", "field")
            assert len(symbols) == 1
            assert symbols[0]["module"] == "my_module"

    def test_postgres_backend_requires_dsn(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_fixture_addon(workspace)

        result = CliRunner().invoke(
            main,
            [str(workspace), "--repo-id", "test-repo", "--odoo-version", "17.0", "--backend", "postgres"],
        )

        assert result.exit_code != 0
        assert "--dsn is required" in result.output
