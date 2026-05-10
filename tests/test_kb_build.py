# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from oops.kb.build import build_project_kb, compute_root_drift, is_project_kb_stale
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

    def test_module_in_list_but_no_symlink_skipped(self, tmp_path):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")

        db_path = build_project_kb(
            repo, "17.0", ["module_a", "module_ghost"], global_kb=global_kb
        )

        with KBReader(db_path) as kb:
            modules = kb.get_modules()
        # module_ghost has no source on disk; it stays absent from the modules table
        assert "module_a" in modules
        assert "module_ghost" not in modules

    def test_symlink_not_in_list_skipped(self, tmp_path):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a", "module_extra")

        db_path = build_project_kb(repo, "17.0", ["module_a"], global_kb=global_kb)

        with KBReader(db_path) as kb:
            modules = kb.get_modules()
        assert "module_extra" not in modules

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

    def test_local_tier_scanned_when_manifest_at_root(self, tmp_path):
        global_kb = _make_global_kb(tmp_path / "global.db")
        repo = tmp_path / "repo"
        repo.mkdir()
        local = repo / "module_local"
        local.mkdir()
        (local / "__manifest__.py").write_text(
            "{'name': 'Local', 'depends': ['base']}", encoding="utf-8"
        )

        db_path = build_project_kb(repo, "17.0", ["module_local"], global_kb=global_kb)

        with KBReader(db_path) as kb:
            modules = kb.get_modules()
            sources = kb.get_sources()
        assert "module_local" in modules
        assert sources.get("local") == str(repo)


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


# ---------------------------------------------------------------------------
# TestComputeRootDrift
# ---------------------------------------------------------------------------


class TestComputeRootDrift:
    def test_missing_at_root_when_module_listed_but_no_symlink(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")
        missing, extra = compute_root_drift(repo, ["module_a", "module_ghost"])
        assert missing == ["module_ghost"]
        assert extra == []

    def test_extra_at_root_when_symlink_not_listed(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a", "module_extra")
        missing, extra = compute_root_drift(repo, ["module_a"])
        assert missing == []
        assert extra == ["module_extra"]

    def test_local_dir_counts_as_at_root(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        local = repo / "module_local"
        local.mkdir()
        (local / "__manifest__.py").write_text(
            "{'name': 'L', 'depends': []}", encoding="utf-8"
        )
        missing, extra = compute_root_drift(repo, ["module_local"])
        assert missing == []
        assert extra == []

    def test_no_drift_when_perfectly_aligned(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_tp_symlinks(repo, "module_a")
        missing, extra = compute_root_drift(repo, ["module_a"])
        assert missing == []
        assert extra == []


# ---------------------------------------------------------------------------
# TestResolvePrototypeRoles
# ---------------------------------------------------------------------------


class TestResolvePrototypeRoles:
    def _make_entry(self, model, module, role, model_type="model", inherit=None):
        return {
            "model": model, "module": module, "origin": "local",
            "role": role, "model_type": model_type,
            "inherit_json": json.dumps(inherit or []),
            "inherits_json": "{}",
            "source_file": f"{module}/models/{model.replace('.', '_')}.py",
            "source_line": 1,
        }

    def test_mixin_only_stays_create(self):
        """_inherit containing only abstract models does not upgrade to prototype."""
        from oops.kb.build import _resolve_prototype_roles
        results = [{"model_origins": [
            self._make_entry("mail.thread", "mail", "create", model_type="abstract"),
            self._make_entry("my.model", "my_module", "create", inherit=["mail.thread"]),
        ]}]
        _resolve_prototype_roles(results)
        entry = next(e for e in results[0]["model_origins"] if e["model"] == "my.model")
        assert entry["role"] == "create"

    def test_concrete_inherit_upgrades_to_prototype(self):
        """_inherit containing a concrete model upgrades to prototype."""
        from oops.kb.build import _resolve_prototype_roles
        results = [{"model_origins": [
            self._make_entry("sale.order", "sale", "create", model_type="model"),
            self._make_entry("my.sale", "my_module", "create", inherit=["sale.order"]),
        ]}]
        _resolve_prototype_roles(results)
        entry = next(e for e in results[0]["model_origins"] if e["model"] == "my.sale")
        assert entry["role"] == "prototype"

    def test_transient_model_not_upgraded_when_inherited_as_abstract(self):
        """TransientModel creators ARE concrete — if inherited by another model, that's prototype."""
        from oops.kb.build import _resolve_prototype_roles
        results = [{"model_origins": [
            self._make_entry("my.wizard", "my_module", "create", model_type="transient"),
            self._make_entry("my.other", "other_module", "create", inherit=["my.wizard"]),
        ]}]
        _resolve_prototype_roles(results)
        entry = next(e for e in results[0]["model_origins"] if e["model"] == "my.other")
        assert entry["role"] == "prototype"

    def test_extend_role_never_upgraded(self):
        """An 'extend' entry is never upgraded regardless of _inherit."""
        from oops.kb.build import _resolve_prototype_roles
        results = [{"model_origins": [
            self._make_entry("sale.order", "sale", "create"),
            self._make_entry("sale.order", "my_module", "extend", inherit=["sale.order"]),
        ]}]
        _resolve_prototype_roles(results)
        entry = next(e for e in results[0]["model_origins"] if e["module"] == "my_module")
        assert entry["role"] == "extend"

    def test_already_prototype_unchanged(self):
        """Idempotent: prototype entries contribute to concrete_models but are not re-processed."""
        from oops.kb.build import _resolve_prototype_roles
        results = [{"model_origins": [
            self._make_entry("sale.order", "sale", "create"),
            self._make_entry("my.sale", "my_module", "prototype", inherit=["sale.order"]),
        ]}]
        _resolve_prototype_roles(results)
        entry = next(e for e in results[0]["model_origins"] if e["model"] == "my.sale")
        assert entry["role"] == "prototype"

    def test_abstract_creator_not_upgraded(self):
        """Abstract model creator is never upgraded to prototype."""
        from oops.kb.build import _resolve_prototype_roles
        results = [{"model_origins": [
            self._make_entry("sale.order", "sale", "create"),
            self._make_entry("my.mixin", "my_module", "create", model_type="abstract", inherit=["sale.order"]),
        ]}]
        _resolve_prototype_roles(results)
        entry = next(e for e in results[0]["model_origins"] if e["model"] == "my.mixin")
        assert entry["role"] == "create"


# ---------------------------------------------------------------------------
# TestKBReaderModelOrigins
# ---------------------------------------------------------------------------


class TestKBReaderModelOrigins:
    def _make_origin_entry(self, model, module, role, model_type="model"):
        return {
            "model": model,
            "module": module,
            "origin": "local",
            "role": role,
            "model_type": model_type,
            "inherit_json": "[]",
            "inherits_json": "{}",
            "source_file": f"{module}/models/x.py",
            "source_line": 1,
        }

    def _db_with_origins(self, tmp_path, origins):
        from oops.kb.store import write_project_kb
        db_path = tmp_path / "test.db"
        write_project_kb(db_path, "17.0", "test", [], {"odoo": "/odoo"}, [
            {"modules": {}, "symbols": [], "field_refs": [], "model_origins": origins}
        ])
        return db_path

    def test_is_model_creator_returns_true_for_create_role(self, tmp_path):
        db = self._db_with_origins(tmp_path, [
            self._make_origin_entry("res.client", "partner_hub", "create"),
        ])
        with KBReader(db) as kb:
            assert kb.is_model_creator("res.client", "partner_hub") is True

    def test_is_model_creator_returns_false_for_extend_role(self, tmp_path):
        db = self._db_with_origins(tmp_path, [
            self._make_origin_entry("res.client", "partner_hub_project", "extend"),
        ])
        with KBReader(db) as kb:
            assert kb.is_model_creator("res.client", "partner_hub_project") is False

    def test_is_model_creator_returns_true_for_prototype_role(self, tmp_path):
        db = self._db_with_origins(tmp_path, [
            self._make_origin_entry("my.sale", "my_module", "prototype"),
        ])
        with KBReader(db) as kb:
            assert kb.is_model_creator("my.sale", "my_module") is True

    def test_is_model_creator_fallback_when_no_model_origins(self, tmp_path):
        """No model_origins rows at all → module assumed to be creator."""
        db = self._db_with_origins(tmp_path, [])
        with KBReader(db) as kb:
            assert kb.is_model_creator("res.client", "partner_hub") is True

    def test_is_model_creator_fallback_false_when_other_creator_exists(self, tmp_path):
        """Module not in model_origins but another module IS creator → returns False."""
        db = self._db_with_origins(tmp_path, [
            self._make_origin_entry("res.client", "other_module", "create"),
        ])
        with KBReader(db) as kb:
            assert kb.is_model_creator("res.client", "unknown_module") is False

    def test_get_model_creators_returns_only_create_and_prototype(self, tmp_path):
        db = self._db_with_origins(tmp_path, [
            self._make_origin_entry("res.client", "partner_hub", "create"),
            self._make_origin_entry("res.client", "partner_hub_project", "extend"),
        ])
        with KBReader(db) as kb:
            creators = kb.get_model_creators("res.client")
        assert len(creators) == 1
        assert creators[0]["module"] == "partner_hub"

    def test_get_model_origin_returns_role(self, tmp_path):
        db = self._db_with_origins(tmp_path, [
            self._make_origin_entry("res.client", "partner_hub", "create"),
        ])
        with KBReader(db) as kb:
            assert kb.get_model_origin("res.client", "partner_hub") == "create"
            assert kb.get_model_origin("res.client", "unknown") is None
