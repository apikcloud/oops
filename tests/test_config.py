from dataclasses import dataclass, field
from pathlib import Path

import pytest
from oops.core.config import _MISSING, Config, ConfigurationError, _apply, _is_list_of_path, load_config
from oops_engine.compat import List

# ---------------------------------------------------------------------------
# _is_list_of_path
# ---------------------------------------------------------------------------


class TestIsListOfPath:
    def test_list_of_path_true(self):
        assert _is_list_of_path(List[Path]) is True

    def test_list_of_str_false(self):
        assert _is_list_of_path(List[str]) is False

    def test_plain_list_false(self):
        assert _is_list_of_path(list) is False

    def test_none_false(self):
        assert _is_list_of_path(None) is False


# ---------------------------------------------------------------------------
# _apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_scalar(self):
        cfg = Config()
        _apply(cfg, {"default_timeout": 120})
        assert cfg.default_timeout == 120

    def test_unknown_key_ignored(self):
        cfg = Config()
        _apply(cfg, {"nonexistent_key": "value"})  # must not raise

    def test_nested_dataclass(self):
        cfg = Config()
        _apply(cfg, {"submodules": {"force_scheme": "https"}})
        assert cfg.submodules.force_scheme == "https"

    def test_path_field(self):
        cfg = Config()
        _apply(cfg, {"submodules": {"current_path": "/tmp/custom"}})
        assert cfg.submodules.current_path == Path("/tmp/custom")

    def test_list_of_path_non_empty_default(self):
        cfg = Config()
        _apply(cfg, {"submodules": {"old_paths": ["a", "b"]}})
        assert cfg.submodules.old_paths == [Path("a"), Path("b")]

    def test_list_of_path_empty_default(self):
        @dataclass
        class _Temp:
            paths: List[Path] = field(default_factory=list)

        obj = _Temp()
        assert obj.paths == []  # confirm default is empty
        _apply(obj, {"paths": ["x", "y"]})
        assert obj.paths == [Path("x"), Path("y")]

    def test_set_field_from_list(self):
        cfg = Config()
        _apply(cfg, {"project": {"mandatory_files": ["a.txt", "b.txt"]}})
        assert cfg.project.mandatory_files == {"a.txt", "b.txt"}
        assert isinstance(cfg.project.mandatory_files, set)

    def test_dict_field_replaced_wholesale(self):
        cfg = Config()
        _apply(cfg, {"submodules": {"deprecated_repositories": {"foo/bar": "foo/baz"}}})
        assert cfg.submodules.deprecated_repositories == {"foo/bar": "foo/baz"}

    def test_multiple_nested_keys(self):
        cfg = Config()
        _apply(cfg, {"images": {"release_warn_age_days": 7, "collections": ["prod"]}})
        assert cfg.images.release_warn_age_days == 7
        assert cfg.images.collections == ["prod"]


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

REQUIRED_YAML = (
    "version: 1\nimages:\n  source:\n    repository: test/repo\n    file: tags.json\nmanifest:\n  author: Apik\n"
)


class TestValidate:
    def test_missing_required_fields_raises(self, tmp_path, monkeypatch):
        empty = tmp_path / ".oops.yaml"
        empty.write_text("")
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [empty])
        with pytest.raises(ConfigurationError, match="images.source.repository"):
            load_config()

    def test_error_lists_all_missing_fields(self, tmp_path, monkeypatch):
        empty = tmp_path / ".oops.yaml"
        empty.write_text("")
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [empty])
        with pytest.raises(ConfigurationError) as exc_info:
            load_config()
        msg = str(exc_info.value)
        assert "images.source.repository" in msg
        assert "images.source.file" in msg
        assert "version" in msg

    def test_sentinel_value(self):
        src = Config().images.source
        assert src.repository is _MISSING
        assert src.file is _MISSING


class TestLoadConfig:
    def test_raises_when_no_file(self, monkeypatch):
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [])
        with pytest.raises(ConfigurationError, match="No config file found"):
            load_config()

    def test_loads_with_required_fields(self, tmp_path, monkeypatch):
        local = tmp_path / ".oops.yaml"
        local.write_text(REQUIRED_YAML)
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [local])
        cfg = load_config()
        assert isinstance(cfg, Config)
        assert cfg.images.source.repository == "test/repo"
        assert cfg.submodules.current_path == Path(".third-party")
        assert cfg.submodules.force_scheme == "ssh"

    def test_local_file_overrides_defaults(self, tmp_path, monkeypatch):
        local = tmp_path / ".oops.yaml"
        local.write_text(REQUIRED_YAML + "submodules:\n  force_scheme: https\n")
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [local])
        cfg = load_config()
        assert cfg.submodules.force_scheme == "https"

    def test_later_path_takes_precedence(self, tmp_path, monkeypatch):
        global_file = tmp_path / "global.yaml"
        local_file = tmp_path / "local.yaml"
        global_file.write_text(REQUIRED_YAML + "submodules:\n  force_scheme: https\n")
        local_file.write_text("submodules:\n  force_scheme: ssh\n")
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [global_file, local_file])
        cfg = load_config()
        assert cfg.submodules.force_scheme == "ssh"

    def test_empty_yaml_raises_missing_fields(self, tmp_path, monkeypatch):
        empty = tmp_path / ".oops.yaml"
        empty.write_text("")
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [empty])
        with pytest.raises(ConfigurationError, match="Missing required"):
            load_config()

    def test_nonexistent_file_raises_no_config(self, tmp_path, monkeypatch):
        missing = tmp_path / "nonexistent.yaml"
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [missing])
        with pytest.raises(ConfigurationError, match="No config file found"):
            load_config()


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------


class TestClassificationConfig:
    def _load(self, tmp_path, monkeypatch, section: str) -> Config:
        local = tmp_path / ".oops.yaml"
        local.write_text(REQUIRED_YAML + section)
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [local])
        return load_config()

    def test_absent_section_defaults_to_empty(self, tmp_path, monkeypatch):
        assert self._load(tmp_path, monkeypatch, "").classification == {}

    def test_empty_section_defaults_to_empty(self, tmp_path, monkeypatch):
        assert self._load(tmp_path, monkeypatch, "classification:\n").classification == {}

    def test_empty_class_is_dropped(self, tmp_path, monkeypatch):
        cfg = self._load(tmp_path, monkeypatch, "classification:\n  oca:\n  custom:\n    - a\n")
        assert cfg.classification == {"custom": ["a"]}

    def test_loads_all_classes(self, tmp_path, monkeypatch):
        section = (
            "classification:\n"
            "  custom:\n    - 'legacy_*'\n    - unprefixed_addon\n"
            "  oca:\n    - forked_module\n"
            "  third-party:\n    - vendored\n"
        )
        assert self._load(tmp_path, monkeypatch, section).classification == {
            "custom": ["legacy_*", "unprefixed_addon"],
            "oca": ["forked_module"],
            "third-party": ["vendored"],
        }

    def test_overlapping_globs_are_accepted_at_load(self, tmp_path, monkeypatch):
        # Only a real addon name can reveal such a conflict: see match_classification.
        section = "classification:\n  custom:\n    - 'acme_*'\n  third-party:\n    - '*_sale'\n"
        assert self._load(tmp_path, monkeypatch, section).classification

    def test_rejects_unknown_class(self, tmp_path, monkeypatch):
        with pytest.raises(ConfigurationError, match="third_party"):
            self._load(tmp_path, monkeypatch, "classification:\n  third_party:\n    - a\n")

    def test_rejects_section_that_is_not_a_mapping(self, tmp_path, monkeypatch):
        with pytest.raises(ConfigurationError, match="classification"):
            self._load(tmp_path, monkeypatch, "classification: custom\n")

    def test_rejects_scalar_instead_of_list(self, tmp_path, monkeypatch):
        with pytest.raises(ConfigurationError, match="classification.custom"):
            self._load(tmp_path, monkeypatch, "classification:\n  custom: 'legacy_*'\n")

    def test_rejects_non_string_pattern(self, tmp_path, monkeypatch):
        with pytest.raises(ConfigurationError, match="classification.custom"):
            self._load(tmp_path, monkeypatch, "classification:\n  custom:\n    - 12\n")

    def test_rejects_same_pattern_in_two_classes(self, tmp_path, monkeypatch):
        section = "classification:\n  custom:\n    - sale_x\n  oca:\n    - sale_x\n"
        with pytest.raises(ConfigurationError, match="sale_x"):
            self._load(tmp_path, monkeypatch, section)

    def test_local_section_replaces_global_one(self, tmp_path, monkeypatch):
        global_file = tmp_path / "global.yaml"
        global_file.write_text(REQUIRED_YAML + "classification:\n  custom:\n    - from_global\n")
        local_file = tmp_path / "local.yaml"
        local_file.write_text("version: 1\nclassification:\n  oca:\n    - from_local\n")
        monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [global_file, local_file])
        assert load_config().classification == {"oca": ["from_local"]}
