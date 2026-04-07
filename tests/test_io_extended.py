"""Tests for oops/io/manifest.py, oops/io/tools.py, and additional oops/io/file.py coverage."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oops.io.file import (
    check_prefix,
    ensure_parent,
    is_dir_empty,
    parse_text_file,
    relpath,
    write_text_file,
)
from oops.io.manifest import (
    find_addons_extended,
    find_manifests,
    get_manifest_path,
    load_manifest,
    parse_manifest,
    parse_manifest_cst,
    read_manifest,
)
from oops.io.tools import ask, get_exec_dir, run


# ---------------------------------------------------------------------------
# oops/io/tools.py
# ---------------------------------------------------------------------------


class TestAsk:
    def test_returns_input_when_provided(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda prompt: "n")
        assert ask("Continue? ") == "n"

    def test_returns_default_on_empty_input(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda prompt: "")
        assert ask("Continue? ", default="y") == "y"

    def test_returns_default_on_eof(self, monkeypatch):
        def raise_eof(prompt):
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        assert ask("Continue? ", default="y") == "y"


class TestGetExecDir:
    def test_returns_string(self):
        d = get_exec_dir()
        assert isinstance(d, str)

    def test_contains_tools_module_dir(self):
        import oops.io.tools as tools_mod
        import os
        expected = os.path.dirname(tools_mod.__file__)
        assert get_exec_dir() == expected


class TestRun:
    def test_run_without_capture(self):
        # Should run echo without capturing — returns None
        result = run(["echo", "hello"], capture=False)
        assert result is None

    def test_run_with_capture(self):
        result = run(["echo", "hello"], capture=True)
        assert "hello" in result

    def test_run_with_cwd(self, tmp_path):
        result = run(["pwd"], capture=True, cwd=str(tmp_path))
        assert str(tmp_path) in result

    def test_run_raises_on_error_with_check(self):
        with pytest.raises(subprocess.CalledProcessError):
            run(["false"], check=True)

    def test_run_no_raise_with_check_false(self):
        # Should not raise even if command fails
        run(["false"], check=False)


# ---------------------------------------------------------------------------
# oops/io/manifest.py
# ---------------------------------------------------------------------------


MANIFEST_SRC = """\
{
    "name": "Test Addon",
    "version": "16.0.1.0.0",
    "summary": "A test addon.",
    "author": "Acme",
    "installable": True,
}
"""


class TestParseManifest:
    def test_parses_manifest_from_file(self, tmp_path):
        f = tmp_path / "__manifest__.py"
        f.write_text(MANIFEST_SRC)
        result = parse_manifest(f)
        assert result["name"] == "Test Addon"
        assert result["version"] == "16.0.1.0.0"

    def test_returns_empty_dict_for_non_dict(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text('"just a string"')
        result = parse_manifest(f)
        assert result == {}


class TestLoadManifest:
    def test_loads_from_addon_dir(self, tmp_path):
        addon = tmp_path / "my_addon"
        addon.mkdir()
        (addon / "__manifest__.py").write_text(MANIFEST_SRC)
        result = load_manifest(addon)
        assert result["name"] == "Test Addon"

    def test_returns_empty_dict_when_no_manifest(self, tmp_path):
        addon = tmp_path / "empty"
        addon.mkdir()
        result = load_manifest(addon)
        assert result == {}


class TestParseManifestCst:
    def test_parses_to_module(self):
        import libcst as cst
        node = parse_manifest_cst(MANIFEST_SRC)
        assert isinstance(node, cst.Module)


class TestReadManifest:
    def test_reads_manifest_from_addon_dir(self, tmp_path):
        import libcst as cst
        (tmp_path / "__manifest__.py").write_text(MANIFEST_SRC)
        node = read_manifest(str(tmp_path))
        assert isinstance(node, cst.Module)

    def test_raises_no_manifest_found(self, tmp_path):
        from oops.core.exceptions import NoManifestFound
        with pytest.raises(NoManifestFound):
            read_manifest(str(tmp_path))


class TestGetManifestPath:
    def test_returns_path_when_manifest_exists(self, tmp_path):
        (tmp_path / "__manifest__.py").write_text(MANIFEST_SRC)
        result = get_manifest_path(str(tmp_path))
        assert result is not None
        assert "__manifest__.py" in result

    def test_returns_none_when_no_manifest(self, tmp_path):
        result = get_manifest_path(str(tmp_path))
        assert result is None


class TestFindAddonsExtended:
    def _create_addon(self, base, name, installable=True):
        addon = base / name
        addon.mkdir()
        src = f'{{"name": "{name}", "installable": {str(installable)}}}'
        (addon / "__manifest__.py").write_text(src)
        return addon

    def test_yields_addon_name_path_manifest(self, tmp_path):
        self._create_addon(tmp_path, "addon_a")
        results = list(find_addons_extended(tmp_path))
        assert len(results) == 1
        name, path, manifest = results[0]
        assert name == "addon_a"
        assert manifest["name"] == "addon_a"

    def test_skips_dirs_without_manifest(self, tmp_path):
        (tmp_path / "not_an_addon").mkdir()
        self._create_addon(tmp_path, "real_addon")
        results = list(find_addons_extended(tmp_path))
        assert len(results) == 1

    def test_installable_only_filter(self, tmp_path):
        self._create_addon(tmp_path, "active", installable=True)
        self._create_addon(tmp_path, "inactive", installable=False)
        results = list(find_addons_extended(tmp_path, installable_only=True))
        names = [r[0] for r in results]
        assert "active" in names
        assert "inactive" not in names

    def test_names_filter(self, tmp_path):
        self._create_addon(tmp_path, "wanted")
        self._create_addon(tmp_path, "unwanted")
        results = list(find_addons_extended(tmp_path, names=["wanted"]))
        assert len(results) == 1
        assert results[0][0] == "wanted"

    def test_accepts_string_path(self, tmp_path):
        self._create_addon(tmp_path, "addon_x")
        results = list(find_addons_extended(str(tmp_path)))
        assert len(results) == 1


class TestFindManifests:
    def test_yields_manifest_paths(self, tmp_path):
        addon = tmp_path / "my_addon"
        addon.mkdir()
        (addon / "__manifest__.py").write_text(MANIFEST_SRC)
        results = list(find_manifests(str(tmp_path)))
        assert any(r and "__manifest__.py" in r for r in results)

    def test_names_filter(self, tmp_path):
        for name in ["addon_a", "addon_b"]:
            d = tmp_path / name
            d.mkdir()
            (d / "__manifest__.py").write_text(MANIFEST_SRC)
        results = list(find_manifests(str(tmp_path), names=["addon_a"]))
        assert len(results) == 1


# ---------------------------------------------------------------------------
# oops/io/file.py — simple utility functions
# ---------------------------------------------------------------------------


class TestEnsureParent:
    def test_creates_parent_directory(self, tmp_path):
        target = tmp_path / "subdir" / "file.txt"
        ensure_parent(target)
        assert target.parent.exists()

    def test_idempotent_when_parent_exists(self, tmp_path):
        target = tmp_path / "file.txt"
        ensure_parent(target)  # parent already exists
        assert target.parent.exists()


class TestIsDirEmpty:
    def test_returns_true_for_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert is_dir_empty(d) is True

    def test_returns_false_for_non_empty_dir(self, tmp_path):
        d = tmp_path / "full"
        d.mkdir()
        (d / "file.txt").write_text("x")
        assert is_dir_empty(d) is False

    def test_returns_false_for_non_existent_path(self, tmp_path):
        assert is_dir_empty(tmp_path / "nonexistent") is False

    def test_returns_false_for_file(self, tmp_path):
        f = tmp_path / "afile.txt"
        f.write_text("data")
        assert is_dir_empty(f) is False


class TestRelpath:
    def test_same_directory(self, tmp_path):
        result = relpath(tmp_path, tmp_path)
        assert result == "."

    def test_child_path(self, tmp_path):
        child = tmp_path / "sub" / "file.txt"
        result = relpath(tmp_path, child)
        assert result == "sub/file.txt"


class TestCheckPrefix:
    def test_exact_match(self, tmp_path):
        assert check_prefix(str(tmp_path), str(tmp_path)) is True

    def test_child_path(self, tmp_path):
        child = str(tmp_path / "subdir")
        assert check_prefix(child, str(tmp_path)) is True

    def test_unrelated_path(self, tmp_path):
        other = tmp_path.parent / "other"
        assert check_prefix(str(other), str(tmp_path)) is False


class TestParseTextFile:
    def test_returns_set_of_lines(self):
        content = "line1\nline2\n\nline3\n"
        result = parse_text_file(content)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_empty_lines_excluded(self):
        result = parse_text_file("\n\n\n")
        assert result == set()


class TestWriteTextFile:
    def test_writes_lines_to_file(self, tmp_path):
        f = tmp_path / "out.txt"
        write_text_file(f, ["a", "b", "c"])
        assert f.read_text() == "a\nb\nc\n"

    def test_no_final_newline(self, tmp_path):
        f = tmp_path / "out.txt"
        write_text_file(f, ["a", "b"], add_final_newline=False)
        assert f.read_text() == "a\nb"

    def test_custom_separator(self, tmp_path):
        f = tmp_path / "out.txt"
        write_text_file(f, ["x", "y"], new_line="|")
        assert f.read_text() == "x|y|"
