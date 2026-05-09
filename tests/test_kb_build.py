# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from oops.kb.build import build_project_kb, is_project_kb_stale
from oops.kb.store import KBReader, write_global_kb

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_global_kb(path: Path, version: str = "17.0") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_global_kb(
        db_path=path,
        odoo_version=version,
        sources={"odoo": "/odoo/src"},
        scan_results=[
            {
                "modules": {"base": {"origin": "odoo", "depends": []}},
                "symbols": [
                    {
                        "model": "res.partner",
                        "name": "name",
                        "kind": "field",
                        "origin": "odoo",
                        "module": "base",
                        "source_file": "/odoo/src/base/models/res_partner.py",
                        "source_line": 10,
                    }
                ],
            }
        ],
    )
    return path


def _make_module(parent: Path, name: str) -> Path:
    """Create a minimal Odoo module directory (no models, just a manifest)."""
    mod = parent / name
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "__manifest__.py").write_text(
        "{'name': 'Test', 'depends': ['base']}", encoding="utf-8"
    )
    return mod


def _make_tp_symlinks(repo: Path, *names: str) -> None:
    """Create .third-party modules and symlinks in repo root for each name."""
    tp_dir = repo / ".third-party"
    for name in names:
        _make_module(tp_dir, name)
        (repo / name).symlink_to(tp_dir / name)


# ---------------------------------------------------------------------------
# Phase 2: build_project_kb
# ---------------------------------------------------------------------------


class TestBuildProjectKb:
    def test_happy_path_scope_matches_input(self, tmp_path):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a", "module_b")

        db_path = build_project_kb(repo, "17.0", ["module_a", "module_b"], global_kb=global_kb)

        assert db_path.exists()
        with KBReader(db_path) as kb:
            meta = kb.get_meta()
            assert json.loads(meta["scope"]) == ["module_a", "module_b"]

    def test_module_in_list_but_no_symlink_warns(self, tmp_path, monkeypatch):
        warnings: list[str] = []
        monkeypatch.setattr("oops.kb.build.print_warning", lambda m: warnings.append(m))

        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")

        db_path = build_project_kb(
            repo, "17.0", ["module_a", "module_ghost"], global_kb=global_kb
        )

        assert any("module_ghost" in w for w in warnings)
        # Ghost module appears in scope (it was in the input list)
        with KBReader(db_path) as kb:
            assert "module_ghost" in json.loads(kb.get_meta()["scope"])

    def test_symlink_not_in_list_warns_and_not_scanned(self, tmp_path, monkeypatch):
        warnings: list[str] = []
        monkeypatch.setattr("oops.kb.build.print_warning", lambda m: warnings.append(m))

        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a", "module_extra")

        build_project_kb(repo, "17.0", ["module_a"], global_kb=global_kb)

        assert any("module_extra" in w for w in warnings)

    def test_missing_global_kb_raises(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        missing = tmp_path / "nonexistent.db"

        with pytest.raises(FileNotFoundError, match="Global KB not found"):
            build_project_kb(repo, "17.0", ["module_a"], global_kb=missing)

    def test_slug_override_in_meta(self, tmp_path):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")

        db_path = build_project_kb(
            repo, "17.0", ["module_a"], slug="my-slug", global_kb=global_kb
        )

        with KBReader(db_path) as kb:
            assert kb.get_meta()["project"] == "my-slug"

    def test_default_slug_is_repo_name(self, tmp_path):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "my-project"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")

        db_path = build_project_kb(repo, "17.0", ["module_a"], global_kb=global_kb)

        with KBReader(db_path) as kb:
            assert kb.get_meta()["project"] == "my-project"


# ---------------------------------------------------------------------------
# Phase 3: is_project_kb_stale
# ---------------------------------------------------------------------------


def _set_kb_generated_at(db_path: Path, ts: datetime) -> None:
    """Overwrite the meta.generated_at row in a KB with a specific timestamp."""
    con = sqlite3.connect(str(db_path))
    con.execute(
        "UPDATE meta SET value = ? WHERE key = 'generated_at'",
        (ts.isoformat(),),
    )
    con.commit()
    con.close()


class TestStaleness:
    def test_no_project_kb(self, tmp_path):
        stale, reason = is_project_kb_stale(tmp_path, "17.0")
        assert stale is True
        assert "no project KB" in reason

    def test_fresh_no_installed_modules_no_global(self, tmp_path):
        # Build a project KB so it exists
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")
        build_project_kb(repo, "17.0", ["module_a"], global_kb=global_kb)

        # Now check staleness without installed_modules.txt and without a global KB at default path
        stale, reason = is_project_kb_stale(repo, "99.0")  # version with no global KB
        assert stale is False
        assert reason == ""

    def test_installed_modules_newer(self, tmp_path):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")
        build_project_kb(repo, "17.0", ["module_a"], global_kb=global_kb)

        # Set project KB generated_at to the past
        project_db = repo / ".oops-cache" / "kb.db"
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        _set_kb_generated_at(project_db, past)

        # Touch installed_modules.txt with a newer mtime
        modules_file = repo / "installed_modules.txt"
        modules_file.write_text("module_a\n", encoding="utf-8")
        future_ts = past.timestamp() + 3600
        os.utime(modules_file, (future_ts, future_ts))

        stale, reason = is_project_kb_stale(repo, "17.0")
        assert stale is True
        assert "installed_modules.txt" in reason

    def test_global_kb_newer(self, tmp_path, monkeypatch):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")
        build_project_kb(repo, "17.0", ["module_a"], global_kb=global_kb)

        # Make project KB older than global KB
        project_db = repo / ".oops-cache" / "kb.db"
        old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
        _set_kb_generated_at(project_db, old_ts)
        new_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        _set_kb_generated_at(global_kb, new_ts)

        # Point staleness check at our tmp global KB
        monkeypatch.setattr("oops.kb.build.global_kb_path", lambda _v: global_kb)

        stale, reason = is_project_kb_stale(repo, "17.0")
        assert stale is True
        assert "global KB" in reason

    def test_corrupted_generated_at(self, tmp_path):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")
        build_project_kb(repo, "17.0", ["module_a"], global_kb=global_kb)

        project_db = repo / ".oops-cache" / "kb.db"
        con = sqlite3.connect(str(project_db))
        con.execute("UPDATE meta SET value = 'not-a-date' WHERE key = 'generated_at'")
        con.commit()
        con.close()

        stale, reason = is_project_kb_stale(repo, "17.0")
        assert stale is True
        assert "generated_at" in reason

    def test_all_fresh(self, tmp_path, monkeypatch):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")
        build_project_kb(repo, "17.0", ["module_a"], global_kb=global_kb)

        # Make global KB older than project KB
        project_db = repo / ".oops-cache" / "kb.db"
        new_ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
        _set_kb_generated_at(project_db, new_ts)
        _set_kb_generated_at(global_kb, old_ts)

        monkeypatch.setattr("oops.kb.build.global_kb_path", lambda _v: global_kb)

        stale, reason = is_project_kb_stale(repo, "17.0")
        assert stale is False
        assert reason == ""
