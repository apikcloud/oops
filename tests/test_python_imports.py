# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_python_imports.py — tests/test_python_imports.py

"""Tests for oops/io/python_imports.py."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from oops.io.python_imports import discover_imported_files


class TestDiscoverImportedFiles:
    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        assert discover_imported_files(tmp_path / "nonexistent") == []

    def test_no_init_returns_empty(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "a.py").write_text("x = 1")
        assert discover_imported_files(pkg) == []

    def test_empty_init_returns_empty(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("x = 1")
        assert discover_imported_files(pkg) == []

    def test_single_relative_import(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import a")
        (pkg / "a.py").write_text("x = 1")
        result = discover_imported_files(pkg)
        assert result == [(pkg / "a.py").resolve()]

    def test_multi_name_relative_import(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import a, b, c")
        for name in ("a", "b", "c"):
            (pkg / f"{name}.py").write_text(f"{name} = 1")
        result = discover_imported_files(pkg)
        assert result == [
            (pkg / "a.py").resolve(),
            (pkg / "b.py").resolve(),
            (pkg / "c.py").resolve(),
        ]

    def test_unreferenced_files_ignored(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import a")
        (pkg / "a.py").write_text("a = 1")
        (pkg / "b.py").write_text("b = 1")
        (pkg / "c.py").write_text("c = 1")
        result = discover_imported_files(pkg)
        assert result == [(pkg / "a.py").resolve()]

    def test_recursive_subpackage(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import sub")
        sub = pkg / "sub"
        sub.mkdir()
        (sub / "__init__.py").write_text("from . import x")
        (sub / "x.py").write_text("x = 1")
        result = discover_imported_files(pkg)
        assert result == [(sub / "x.py").resolve()]

    def test_from_subpackage_import_member(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .sub import x")
        sub = pkg / "sub"
        sub.mkdir()
        (sub / "__init__.py").write_text("from . import x")
        (sub / "x.py").write_text("x = 1")
        result = discover_imported_files(pkg)
        assert result == [(sub / "x.py").resolve()]

    def test_from_subpackage_import_member_flat_file(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .sub import something")
        # sub is a plain file, not a package — so node.module='sub' resolves to sub.py
        (pkg / "sub.py").write_text("something = 1")
        result = discover_imported_files(pkg)
        assert result == [(pkg / "sub.py").resolve()]

    def test_absolute_imports_skipped(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from odoo import models\nfrom . import a")
        (pkg / "a.py").write_text("a = 1")
        result = discover_imported_files(pkg)
        assert result == [(pkg / "a.py").resolve()]

    def test_syntax_error_returns_empty_with_log(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import (")  # syntax error
        with caplog.at_level(logging.DEBUG, logger="oops"):
            result = discover_imported_files(pkg)
        assert result == []
        assert any("parse failed" in r.message for r in caplog.records)

    def test_dedup_on_multiple_paths_to_same_file(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        # Two import lines that both try to resolve to a.py
        (pkg / "__init__.py").write_text("from . import a\nfrom . import a")
        (pkg / "a.py").write_text("a = 1")
        result = discover_imported_files(pkg)
        assert result == [(pkg / "a.py").resolve()]

    def test_init_py_itself_excluded(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import sub")
        sub = pkg / "sub"
        sub.mkdir()
        (sub / "__init__.py").write_text("from . import x")
        (sub / "x.py").write_text("x = 1")
        result = discover_imported_files(pkg)
        init_files = [p for p in result if p.name == "__init__.py"]
        assert init_files == []
        assert (sub / "x.py").resolve() in result

    def test_non_import_stmt_skipped(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("x = 1\nfrom . import a")
        (pkg / "a.py").write_text("a = 1")
        result = discover_imported_files(pkg)
        assert result == [(pkg / "a.py").resolve()]

    def test_from_nonexistent_module_import_ignored(self, tmp_path: Path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .ghost import something\nfrom . import a")
        (pkg / "a.py").write_text("a = 1")
        result = discover_imported_files(pkg)
        assert result == [(pkg / "a.py").resolve()]

    def test_resolve_name_to_nothing_ignored(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import ghost\nfrom . import a")
        (pkg / "a.py").write_text("a = 1")
        with caplog.at_level(logging.DEBUG, logger="oops"):
            result = discover_imported_files(pkg)
        assert result == [(pkg / "a.py").resolve()]
        assert any("resolves to nothing" in r.message for r in caplog.records)
