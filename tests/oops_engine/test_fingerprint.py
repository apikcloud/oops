# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_fingerprint.py — tests/oops_engine/test_fingerprint.py

"""Unit tests for oops_engine.fingerprint: fingerprint_directory/chain_fingerprint."""

from __future__ import annotations

import time
from pathlib import Path

from oops_engine.fingerprint import chain_fingerprint, fingerprint_directory


class TestFingerprintDirectory:
    def test_stable_across_reruns_with_no_changes(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
        (tmp_path / "b.py").write_text("y = 2", encoding="utf-8")

        first = fingerprint_directory(tmp_path)
        second = fingerprint_directory(tmp_path)

        assert first == second

    def test_sensitive_to_file_content_and_size_change(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("x = 1", encoding="utf-8")
        before = fingerprint_directory(tmp_path)

        time.sleep(0.01)
        f.write_text("x = 12345", encoding="utf-8")  # different size -> different mtime_ns too
        after = fingerprint_directory(tmp_path)

        assert before != after

    def test_sensitive_to_new_file(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
        before = fingerprint_directory(tmp_path)

        (tmp_path / "b.py").write_text("y = 2", encoding="utf-8")
        after = fingerprint_directory(tmp_path)

        assert before != after

    def test_pycache_and_git_excluded(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
        before = fingerprint_directory(tmp_path)

        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "a.cpython-311.pyc").write_bytes(b"\x00\x01")

        git = tmp_path / ".git"
        git.mkdir()
        (git / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")

        (tmp_path / "a.pyc").write_bytes(b"\x00\x01")

        after = fingerprint_directory(tmp_path)

        assert before == after


class TestChainFingerprint:
    def test_stable_and_deterministic(self) -> None:
        assert chain_fingerprint("own", ["dep1", "dep2"]) == chain_fingerprint("own", ["dep1", "dep2"])

    def test_order_independent(self) -> None:
        assert chain_fingerprint("own", ["dep1", "dep2"]) == chain_fingerprint("own", ["dep2", "dep1"])

    def test_sensitive_to_own_fingerprint_change(self) -> None:
        assert chain_fingerprint("own1", ["dep1"]) != chain_fingerprint("own2", ["dep1"])

    def test_sensitive_to_dependency_fingerprint_change(self) -> None:
        assert chain_fingerprint("own", ["dep1"]) != chain_fingerprint("own", ["dep1-changed"])

    def test_sensitive_to_dependency_set_change(self) -> None:
        assert chain_fingerprint("own", ["dep1"]) != chain_fingerprint("own", ["dep1", "dep2"])

    def test_no_dependencies(self) -> None:
        assert chain_fingerprint("own", []) == chain_fingerprint("own", [])
