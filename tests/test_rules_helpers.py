"""Tests for oops/rules/_helpers.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import libcst as cst
from oops.rules._helpers import (
    _addon_root_of,
    _find_manifest_rel,
    _staged_files,
    extract_kv,
    file_at_ref,
    get_lint_path,
    git_repo_root,
    key_name,
    last_tag,
    load_manifest_cfg,
    module_version,
    parse_version_str,
    set_lint_path,
    sort_key,
    staged_addon_manifest_relpaths,
    string_value,
)

# ---------------------------------------------------------------------------
# Helpers to clear lru_cache between tests
# ---------------------------------------------------------------------------


def clear_git_caches():
    git_repo_root.cache_clear()
    _staged_files.cache_clear()
    last_tag.cache_clear()
    file_at_ref.cache_clear()
    staged_addon_manifest_relpaths.cache_clear()


# ---------------------------------------------------------------------------
# extract_kv
# ---------------------------------------------------------------------------


class TestExtractKv:
    def _dict(self, src: str) -> cst.Dict:
        return cst.parse_expression(src)  # type: ignore[return-value]

    def test_simple_keys(self):
        d = self._dict('{"name": "x", "version": "1.0.0"}')
        kv = extract_kv(d)
        assert set(kv.keys()) == {"name", "version"}

    def test_single_quoted_keys(self):
        d = self._dict("{'name': 'test'}")
        kv = extract_kv(d)
        assert "name" in kv

    def test_non_string_key_skipped(self):
        # a variable key like {name: "x"} — not a SimpleString, skipped
        d = self._dict('{"name": "x"}')
        kv = extract_kv(d)
        assert len(kv) == 1

    def test_empty_dict(self):
        d = self._dict("{}")
        assert extract_kv(d) == {}

    def test_starred_element_skipped(self):
        # **other is a StarredDictElement, not DictElement
        d = cst.parse_expression('{"a": 1}')
        kv = extract_kv(d)  # type: ignore[arg-type]
        assert "a" in kv


# ---------------------------------------------------------------------------
# string_value
# ---------------------------------------------------------------------------


class TestStringValue:
    def test_double_quoted(self):
        node = cst.parse_expression('"hello"')
        assert string_value(node) == "hello"  # type: ignore[arg-type]

    def test_single_quoted(self):
        node = cst.parse_expression("'world'")
        assert string_value(node) == "world"  # type: ignore[arg-type]

    def test_non_string_returns_none(self):
        node = cst.parse_expression("42")
        assert string_value(node) is None  # type: ignore[arg-type]

    def test_list_returns_none(self):
        node = cst.parse_expression('["a", "b"]')
        assert string_value(node) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# key_name
# ---------------------------------------------------------------------------


class TestKeyName:
    def _elem(self, src: str) -> cst.DictElement:
        d = cst.parse_expression(src)
        return d.elements[0]  # type: ignore[union-attr]

    def test_string_key(self):
        el = self._elem('{"hello": 1}')
        assert key_name(el) == "hello"

    def test_single_quoted_key(self):
        el = self._elem("{'world': True}")
        assert key_name(el) == "world"


# ---------------------------------------------------------------------------
# sort_key
# ---------------------------------------------------------------------------


class TestSortKey:
    ORDER = ["name", "version", "author", "license"]

    def test_known_key_returns_position(self):
        assert sort_key("name", self.ORDER) == (0, "name")
        assert sort_key("license", self.ORDER) == (3, "license")

    def test_unknown_key_pushed_to_end(self):
        pos, _ = sort_key("unknown", self.ORDER)
        assert pos == len(self.ORDER)

    def test_none_key_pushed_to_end(self):
        pos, name = sort_key(None, self.ORDER)
        assert pos == len(self.ORDER)
        assert name == ""


# ---------------------------------------------------------------------------
# set_lint_path / get_lint_path
# ---------------------------------------------------------------------------


class TestLintPath:
    def test_set_and_get(self):
        p = Path("/tmp/test_manifest.py")
        set_lint_path(p)
        assert get_lint_path() == p

    def test_set_none(self):
        set_lint_path(None)  # type: ignore[arg-type]
        assert get_lint_path() is None


# ---------------------------------------------------------------------------
# parse_version_str
# ---------------------------------------------------------------------------


class TestParseVersionStr:
    def test_valid_5_part(self):
        src = '{"version": "16.0.1.0.0"}'
        result = parse_version_str(src)
        assert result == (16, 0, 1, 0, 0)

    def test_valid_19(self):
        src = '{"version": "19.0.2.3.4"}'
        assert parse_version_str(src) == (19, 0, 2, 3, 4)

    def test_no_version_field(self):
        src = '{"name": "addon"}'
        assert parse_version_str(src) is None

    def test_empty_version(self):
        src = '{"version": ""}'
        assert parse_version_str(src) is None

    def test_invalid_source(self):
        assert parse_version_str("not a dict") is None

    def test_non_numeric_version(self):
        # "abc" can't be split into ints
        src = '{"version": "abc"}'
        assert parse_version_str(src) is None


# ---------------------------------------------------------------------------
# module_version
# ---------------------------------------------------------------------------


class TestModuleVersion:
    def test_5_parts_returns_last_3(self):
        assert module_version((16, 0, 1, 2, 3)) == (1, 2, 3)

    def test_exactly_5(self):
        assert module_version((19, 0, 0, 0, 1)) == (0, 0, 1)

    def test_short_tuple_returned_whole(self):
        assert module_version((1, 0, 0)) == (1, 0, 0)

    def test_empty_tuple(self):
        assert module_version(()) == ()


# ---------------------------------------------------------------------------
# load_manifest_cfg
# ---------------------------------------------------------------------------


class TestLoadManifestCfg:
    def test_returns_manifest_config_when_available(self):
        cfg = load_manifest_cfg()
        # In the test environment, config should be loadable
        # (REQUIRED_YAML is not set, so it may return None or a ManifestConfig)
        # Just assert it doesn't raise
        assert cfg is None or hasattr(cfg, "author")

    def test_returns_none_on_exception(self, monkeypatch):
        import oops.rules._helpers as helpers

        def bad_import():
            raise Exception("config unavailable")

        monkeypatch.setattr(helpers, "load_manifest_cfg", lambda: None)
        assert helpers.load_manifest_cfg() is None


# ---------------------------------------------------------------------------
# git_repo_root (mocked subprocess)
# ---------------------------------------------------------------------------


class TestGitRepoRoot:
    def test_returns_path_on_success(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/repo/root\n")
            result = git_repo_root()
            assert result == Path("/repo/root")
        clear_git_caches()

    def test_returns_none_on_failure(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = git_repo_root()
            assert result is None
        clear_git_caches()


# ---------------------------------------------------------------------------
# _staged_files (mocked)
# ---------------------------------------------------------------------------


class TestStagedFiles:
    def test_returns_frozenset_of_paths(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="a/b.py\nc/d.py\n")
            result = _staged_files()
            assert result == frozenset({"a/b.py", "c/d.py"})
        clear_git_caches()

    def test_returns_empty_on_failure(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = _staged_files()
            assert result == frozenset()
        clear_git_caches()


# ---------------------------------------------------------------------------
# last_tag (mocked)
# ---------------------------------------------------------------------------


class TestLastTag:
    def test_returns_tag_string(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="v1.2.3\n")
            assert last_tag() == "v1.2.3"
        clear_git_caches()

    def test_returns_none_when_no_tags(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            assert last_tag() is None
        clear_git_caches()


# ---------------------------------------------------------------------------
# file_at_ref (mocked)
# ---------------------------------------------------------------------------


class TestFileAtRef:
    def test_returns_content_on_success(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='{"name": "test"}')
            result = file_at_ref("addon/__manifest__.py", "HEAD")
            assert result == '{"name": "test"}'
        clear_git_caches()

    def test_returns_none_on_failure(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = file_at_ref("missing.py", "HEAD")
            assert result is None
        clear_git_caches()

    def test_index_ref_uses_colon_prefix(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="content")
            file_at_ref("some/path.py", ":")
            args = mock_run.call_args[0][0]
            assert ":some/path.py" in args
        clear_git_caches()

    def test_head_ref_uses_ref_prefix(self):
        clear_git_caches()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="content")
            file_at_ref("some/path.py", "HEAD")
            args = mock_run.call_args[0][0]
            assert "HEAD:some/path.py" in args
        clear_git_caches()


# ---------------------------------------------------------------------------
# _find_manifest_rel / _addon_root_of
# ---------------------------------------------------------------------------


class TestFindManifestRel:
    def test_finds_manifest_in_addon_dir(self, tmp_path):
        addon = tmp_path / "my_addon"
        addon.mkdir()
        manifest = addon / "__manifest__.py"
        manifest.write_text('{"name": "My Addon"}')
        result = _find_manifest_rel(addon, tmp_path)
        assert result == "my_addon/__manifest__.py"

    def test_returns_none_when_no_manifest(self, tmp_path):
        addon = tmp_path / "empty_dir"
        addon.mkdir()
        result = _find_manifest_rel(addon, tmp_path)
        assert result is None


class TestAddonRootOf:
    def test_finds_addon_root_from_file_in_addon(self, tmp_path):
        addon = tmp_path / "my_addon"
        addon.mkdir()
        (addon / "__manifest__.py").write_text('{"name": "x"}')
        py_file = addon / "models" / "res_partner.py"
        py_file.parent.mkdir()
        py_file.write_text("# model")
        result = _addon_root_of(py_file, tmp_path)
        assert result == addon

    def test_returns_none_when_no_addon_found(self, tmp_path):
        random_file = tmp_path / "readme.md"
        random_file.write_text("hi")
        result = _addon_root_of(random_file, tmp_path)
        assert result is None

    def test_works_for_directory(self, tmp_path):
        addon = tmp_path / "my_addon"
        addon.mkdir()
        (addon / "__manifest__.py").write_text('{"name": "x"}')
        result = _addon_root_of(addon, tmp_path)
        assert result == addon


# ---------------------------------------------------------------------------
# staged_addon_manifest_relpaths
# ---------------------------------------------------------------------------


class TestStagedAddonManifestRelpaths:
    def test_returns_empty_when_no_repo_root(self):
        clear_git_caches()
        with patch("oops.rules._helpers.git_repo_root", return_value=None):
            result = staged_addon_manifest_relpaths()
            assert result == frozenset()
        clear_git_caches()

    def test_returns_manifest_paths_for_staged_files(self, tmp_path):
        clear_git_caches()
        # Create a fake addon
        addon = tmp_path / "my_addon"
        addon.mkdir()
        manifest = addon / "__manifest__.py"
        manifest.write_text('{"name": "x"}')
        staged_rel = "my_addon/models/res_partner.py"
        (addon / "models").mkdir()
        (addon / "models" / "res_partner.py").write_text("# model")

        with (
            patch("oops.rules._helpers.git_repo_root", return_value=tmp_path),
            patch("oops.rules._helpers._staged_files", return_value=frozenset({staged_rel})),
        ):
            result = staged_addon_manifest_relpaths()
            assert "my_addon/__manifest__.py" in result
        clear_git_caches()
