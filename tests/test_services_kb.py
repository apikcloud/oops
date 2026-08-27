# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_services_kb.py — tests/test_services_kb.py

"""Tests for oops/services/kb.py — the CLI<->engine bridge."""

from __future__ import annotations

from pathlib import Path

from git import Repo
from oops.services.kb import discover_project_addons


def _make_module(parent: Path, name: str, author: str | None = None) -> Path:
    mod = parent / name
    mod.mkdir(parents=True, exist_ok=True)
    manifest = {"name": "Test", "depends": ["base"]}
    if author is not None:
        manifest["author"] = author
    (mod / "__manifest__.py").write_text(repr(manifest), encoding="utf-8")
    return mod


class TestDiscoverProjectAddons:
    def test_classifies_and_filters_by_allowed_modules(self, tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)

        tp_dir = repo_path / ".third-party"
        _make_module(tp_dir, "module_a")
        (repo_path / "module_a").symlink_to(tp_dir / "module_a")
        _make_module(tp_dir, "module_extra")
        (repo_path / "module_extra").symlink_to(tp_dir / "module_extra")

        _make_module(repo_path, "module_local", author="Acme")  # matches conftest's config.manifest.author

        addons = discover_project_addons(repo, repo_path, {"module_a", "module_local"})

        names = {a.technical_name for a in addons}
        assert names == {"module_a", "module_local"}

        by_name = {a.technical_name: a for a in addons}
        assert by_name["module_a"].classification == "third-party"
        assert by_name["module_local"].classification == "custom"

    def test_sorted_by_technical_name(self, tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)

        _make_module(repo_path, "zeta")
        _make_module(repo_path, "alpha")

        addons = discover_project_addons(repo, repo_path, {"zeta", "alpha"})

        assert [a.technical_name for a in addons] == ["alpha", "zeta"]

    def test_dedup_prefers_symlink_over_real_path(self, tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)

        tp_dir = repo_path / ".third-party"
        real = _make_module(tp_dir, "module_a")
        sub = repo_path / "nested"
        sub.mkdir()
        (repo_path / "module_a").symlink_to(real)
        (sub / "module_a").symlink_to(real)

        addons = discover_project_addons(repo, repo_path, {"module_a"})

        assert len(addons) == 1
        assert addons[0].symlinked is True
