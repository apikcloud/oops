# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_addons_analyze_cache.py — tests/test_addons_analyze_cache.py

"""Tests for the per-module analysis cache (Phase 5 of the engine-separation plan).

Covers:
- ModuleSummary.to_cache_dict()/from_dict() round-tripping the non-JSON-native
  fields (Path, frozenset, tuple-keyed dict) that dataclasses.asdict() alone
  cannot serialize.
- oops_engine.store's write_cached_analysis()/KBReader.get_cached_analysis()
  round-trip and repo_id-scoping.
- The `oops addons analyze` read-through cache: a second run reuses the cached
  result instead of re-analysing, --no-cache forces a fresh analysis, and a
  cache hit produces byte-identical JSON output to a fresh run.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.addons.analyze import main
from oops.core.models import ClassSummary, ModuleSummary, Result, StructureSummary
from oops.services.loc import LocStats
from oops_engine.fingerprint import chain_fingerprint, fingerprint_directory
from oops_engine.store import KBReader, write_cached_analysis, write_kb

from .test_analyze import NEW_MODEL_SOURCE, _make_kb, _make_module_full, _mock_analyze

_TEST_REPO_ID = "test"


# ---------------------------------------------------------------------------
# TestModuleSummaryCacheRoundTrip
# ---------------------------------------------------------------------------


class TestModuleSummaryCacheRoundTrip:
    def _make_summary(self, tmp_path: Path) -> ModuleSummary:
        return ModuleSummary(
            module_name="my_module",
            module_path=tmp_path / "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            classes=[
                ClassSummary(
                    class_name="MyModel",
                    is_new_model=True,
                    inherit=[],
                    fields_total=1,
                    fields_base=0,
                    fields_new=1,
                    fields_inherited=0,
                    fields_by_type={"Char": 1},
                    methods_total=1,
                    methods_by_section={"ACTION METHODS": 1},
                    overrides=0,
                    override_details=[],
                    missing_docstrings=1,
                )
            ],
            structure=StructureSummary(
                data={"views": {"xml": 1}},
                demo={},
                controllers_py=0,
                wizard_py=0,
                report_py=0,
                static_by_ext={},
                xml_analysed=frozenset({"views/x.xml"}),
            ),
            loc=LocStats(python=10, xml=5, javascript=0, docs=0),
            loc_pct=42.0,
            method_stacks={("my.model", "action_open"): [{"module": "my_module"}]},
            origin="custom",
        )

    def test_round_trip_preserves_path_frozenset_and_tuple_keys(self, tmp_path: Path) -> None:
        summary = self._make_summary(tmp_path)
        payload = summary.to_cache_dict()

        # Must be genuinely JSON-safe — not just asdict()-safe.
        payload = json.loads(json.dumps(payload))

        restored = ModuleSummary.from_dict(payload)

        assert restored.module_path == summary.module_path
        assert isinstance(restored.module_path, Path)
        assert restored.structure.xml_analysed == summary.structure.xml_analysed
        assert isinstance(restored.structure.xml_analysed, frozenset)
        assert restored.method_stacks == summary.method_stacks
        assert all(isinstance(k, tuple) for k in restored.method_stacks)
        assert restored.classes == summary.classes
        assert restored.loc == summary.loc
        assert restored.origin == summary.origin

    def test_class_infos_round_trip(self, tmp_path: Path) -> None:
        from oops.io.refactor import ClassInfo, SymbolInfo

        summary = self._make_summary(tmp_path)
        summary.class_infos = [
            ClassInfo(
                class_name="MyModel",
                model_name="my.model",
                inherit=[],
                is_new_model=True,
                lineno=1,
                symbols=[
                    SymbolInfo(
                        name="action_open",
                        kind="method",
                        section="ACTION METHODS",
                        lineno=5,
                        end_lineno=6,
                        kb_entry={"module": "base", "origin": "odoo"},
                    )
                ],
            )
        ]
        payload = json.loads(json.dumps(summary.to_cache_dict()))
        restored = ModuleSummary.from_dict(payload)

        assert len(restored.class_infos) == 1
        assert isinstance(restored.class_infos[0], ClassInfo)
        assert isinstance(restored.class_infos[0].symbols[0], SymbolInfo)
        assert restored.class_infos[0].symbols[0].kb_entry == {"module": "base", "origin": "odoo"}


# ---------------------------------------------------------------------------
# TestStoreCacheHelpers
# ---------------------------------------------------------------------------


class TestStoreCacheHelpers:
    def test_write_then_read_cached_analysis(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        write_kb(db_path, _TEST_REPO_ID, "17.0", [], sources={})
        write_cached_analysis(
            db_path, _TEST_REPO_ID, "my_module", "fp-1", "2026-01-01T00:00:00", {"foo": "bar"}
        )

        with KBReader(db_path, repo_ids=[_TEST_REPO_ID]) as kb:
            assert kb.get_cached_analysis("my_module", "fp-1") == {"foo": "bar"}
            assert kb.get_cached_analysis("my_module", "some-other-fingerprint") is None
            assert kb.get_cached_analysis("other_module", "fp-1") is None

    def test_write_kb_no_longer_invalidates_cache_rows(self, tmp_path: Path) -> None:
        """A KB rebuild (write_kb) alone must not invalidate analysis_cache —
        only a content_fingerprint mismatch does. This is the core fix of the
        content-fingerprint cache: previously every KB rebuild wiped every
        module's cached analysis, even for modules whose source didn't change."""
        db_path = tmp_path / "kb.db"
        write_kb(db_path, _TEST_REPO_ID, "17.0", [], sources={})
        write_cached_analysis(
            db_path, _TEST_REPO_ID, "my_module", "fp-1", "gen-1", {"foo": "bar"}
        )

        write_kb(db_path, _TEST_REPO_ID, "17.0", [], sources={})  # simulates a KB rebuild

        with KBReader(db_path, repo_ids=[_TEST_REPO_ID]) as kb:
            assert kb.get_cached_analysis("my_module", "fp-1") == {"foo": "bar"}

    def test_write_cached_analysis_prunes_stale_fingerprints_for_same_module(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        write_kb(db_path, _TEST_REPO_ID, "17.0", [], sources={})
        write_cached_analysis(db_path, _TEST_REPO_ID, "my_module", "fp-1", "gen-1", {"v": 1})
        write_cached_analysis(db_path, _TEST_REPO_ID, "my_module", "fp-2", "gen-1", {"v": 2})

        with KBReader(db_path, repo_ids=[_TEST_REPO_ID]) as kb:
            assert kb.get_cached_analysis("my_module", "fp-1") is None  # pruned
            assert kb.get_cached_analysis("my_module", "fp-2") == {"v": 2}

    def test_cache_is_scoped_by_repo_id(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        write_kb(db_path, "repo-a", "17.0", [], sources={})
        write_kb(db_path, "repo-b", "17.0", [], sources={})
        write_cached_analysis(db_path, "repo-a", "my_module", "fp-1", "gen-1", {"who": "a"})

        with KBReader(db_path, repo_ids=["repo-b"]) as kb:
            assert kb.get_cached_analysis("my_module", "fp-1") is None
        with KBReader(db_path, repo_ids=["repo-a"]) as kb:
            assert kb.get_cached_analysis("my_module", "fp-1") == {"who": "a"}


# ---------------------------------------------------------------------------
# TestAnalyzeCacheIntegration
# ---------------------------------------------------------------------------


class TestAnalyzeCacheIntegration:
    def test_second_run_skips_reanalysis_and_matches_fresh_output(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )

        with _mock_analyze(tmp_path, db_path):
            first = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert first.exit_code == 0, first.output

        with _mock_analyze(tmp_path, db_path), \
                patch("oops.commands.addons.analyze.analyse_file") as mock_analyse:
            second = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert second.exit_code == 0, second.output
        mock_analyse.assert_not_called()

        assert json.loads(first.output)["modules"] == json.loads(second.output)["modules"]

    def test_no_cache_flag_forces_reanalysis(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )

        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0, result.output

        with _mock_analyze(tmp_path, db_path), \
                patch("oops.commands.addons.analyze.analyse_file") as mock_analyse:
            mock_analyse.return_value = []
            result = CliRunner().invoke(main, ["--no-cache", "--format", "json", str(module_path)])
        assert result.exit_code == 0, result.output
        mock_analyse.assert_called()

    def test_cache_populated_after_first_run(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )

        with _mock_analyze(tmp_path, db_path):
            result = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert result.exit_code == 0, result.output

        # "base" is not part of the analyzed set, so it's excluded from the chain.
        content_fingerprint = chain_fingerprint(fingerprint_directory(module_path), [])
        with KBReader(db_path, repo_ids=[_TEST_REPO_ID]) as kb:
            cached = kb.get_cached_analysis("my_module", content_fingerprint)
        assert cached is not None
        assert cached["summary"]["module_name"] == "my_module"
        assert "warnings" in cached
        assert "errors" in cached

    def test_cache_hit_preserves_module_warnings(self, tmp_path: Path) -> None:
        """Regression: a cache hit used to only restore ModuleSummary — the
        per-module Result.warnings (e.g. "models/ has no imported .py files")
        were dropped entirely on the second run."""
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "no_py_files",
            manifest={"name": "No Py Files", "depends": ["base"]},
        )
        (module_path / "models").mkdir()

        with _mock_analyze(tmp_path, db_path):
            first = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert first.exit_code == 0, first.output
        first_warnings = json.loads(first.output)["modules"][0]["warnings"]
        assert any("models/ has no imported .py files" in w for w in first_warnings)

        with _mock_analyze(tmp_path, db_path):
            second = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert second.exit_code == 0, second.output
        second_warnings = json.loads(second.output)["modules"][0]["warnings"]
        assert second_warnings == first_warnings

    def test_refresh_rebuilds_kb_but_reuses_cache_when_unchanged(self, tmp_path: Path) -> None:
        """A --refresh rebuild bumps the KB's generated_at, but the module's
        content_fingerprint is unchanged (no file edits) — so the cache is
        still hit and analyse_file is not called again. This is the core fix
        of content-fingerprint keying: a KB rebuild alone no longer
        invalidates every module's cached analysis (contrast with the old
        kb_generated_at-keyed cache, which made this a guaranteed miss)."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        db_path = repo_path / ".oops-cache" / "kb.db"
        db_path.parent.mkdir()
        _make_kb(db_path)
        module_path = _make_module_full(
            repo_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )

        with _mock_analyze(repo_path, db_path):
            first = CliRunner().invoke(main, ["--format", "json", str(module_path)])
        assert first.exit_code == 0, first.output

        def fake_build(rp, version, modules, addons):  # noqa: ARG001
            write_kb(db_path, _TEST_REPO_ID, "17.0", [], sources={"odoo": "/odoo"})
            return Result(data=db_path)

        with patch("oops.commands.addons.analyze.require_repository") as mock_repo, \
                patch("oops.commands.addons.analyze.require_project", return_value=MagicMock(major_version=17)), \
                patch("oops.commands.addons.analyze.read_installed_modules") as mock_info, \
                patch("oops.commands.addons.analyze.is_project_kb_stale", return_value=(False, "")), \
                patch("oops.commands.addons.analyze.discover_project_addons", return_value=[]), \
                patch("oops.commands.addons.analyze.build_project_kb", side_effect=fake_build), \
                patch("oops.commands.addons.analyze.project_kb_path", return_value=db_path), \
                patch("oops.commands.addons.analyze.local_repo_id", return_value=_TEST_REPO_ID), \
                patch("oops.commands.addons.analyze.analyse_file") as mock_analyse, \
                patch("oops.core.logger.Live", MagicMock()):
            mock_repo.return_value = (MagicMock(), repo_path)
            mock_info.return_value = MagicMock(modules=["my_module"])
            second = CliRunner().invoke(main, ["--refresh", "--format", "json", str(module_path)])
        assert second.exit_code == 0, second.output
        mock_analyse.assert_not_called()


# ---------------------------------------------------------------------------
# TestContentFingerprintCache — dependency-chained cache invalidation
# ---------------------------------------------------------------------------


def _module_names_written(mock_write) -> set:
    """Module names passed to write_cached_analysis (only reached on a cache miss)."""
    return {c.args[2] for c in mock_write.call_args_list}


class TestContentFingerprintCache:
    def _make_dep_and_main(self, tmp_path: Path, db_path: Path) -> "tuple[Path, Path]":
        from oops_engine.store import update_module_load_order

        _make_kb(
            db_path,
            modules={
                "dep_module": {"origin": "custom", "depends": []},
                "main_module": {"origin": "custom", "depends": ["dep_module", "base"]},
            },
        )
        update_module_load_order(db_path, [_TEST_REPO_ID], {"dep_module": (0, 0), "main_module": (1, 1)})

        dep_path = _make_module_full(tmp_path, "dep_module", manifest={"name": "Dep", "depends": []})
        main_path = _make_module_full(
            tmp_path, "main_module", manifest={"name": "Main", "depends": ["dep_module", "base"]}
        )
        return dep_path, main_path

    def test_unchanged_module_cache_hit_after_kb_rebuild(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        dep_path, main_path = self._make_dep_and_main(tmp_path, db_path)

        with _mock_analyze(tmp_path, db_path):
            first = CliRunner().invoke(main, ["--format", "json", str(dep_path), str(main_path)])
        assert first.exit_code == 0, first.output

        _make_kb(  # simulate a KB rebuild — bumps generated_at, no file changes
            db_path,
            modules={
                "dep_module": {"origin": "custom", "depends": []},
                "main_module": {"origin": "custom", "depends": ["dep_module", "base"]},
            },
        )
        from oops_engine.store import update_module_load_order

        update_module_load_order(db_path, [_TEST_REPO_ID], {"dep_module": (0, 0), "main_module": (1, 1)})

        with _mock_analyze(tmp_path, db_path), \
                patch("oops.commands.addons.analyze.write_cached_analysis") as mock_write:
            second = CliRunner().invoke(main, ["--format", "json", str(dep_path), str(main_path)])
        assert second.exit_code == 0, second.output
        assert _module_names_written(mock_write) == set()  # every module hit the cache

    def test_edited_module_cache_miss(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        dep_path, main_path = self._make_dep_and_main(tmp_path, db_path)

        with _mock_analyze(tmp_path, db_path):
            first = CliRunner().invoke(main, ["--format", "json", str(dep_path), str(main_path)])
        assert first.exit_code == 0, first.output

        time.sleep(0.01)
        (main_path / "extra.py").write_text("x = 1", encoding="utf-8")

        with _mock_analyze(tmp_path, db_path), \
                patch("oops.commands.addons.analyze.write_cached_analysis") as mock_write:
            second = CliRunner().invoke(main, ["--format", "json", str(dep_path), str(main_path)])
        assert second.exit_code == 0, second.output
        # Only main_module's own files changed — dep_module is untouched and still hits.
        assert _module_names_written(mock_write) == {"main_module"}

    def test_dependent_module_cache_miss_when_dependency_changes(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        dep_path, main_path = self._make_dep_and_main(tmp_path, db_path)

        with _mock_analyze(tmp_path, db_path):
            first = CliRunner().invoke(main, ["--format", "json", str(dep_path), str(main_path)])
        assert first.exit_code == 0, first.output

        time.sleep(0.01)
        (dep_path / "extra.py").write_text("x = 1", encoding="utf-8")

        with _mock_analyze(tmp_path, db_path), \
                patch("oops.commands.addons.analyze.write_cached_analysis") as mock_write:
            second = CliRunner().invoke(main, ["--format", "json", str(dep_path), str(main_path)])
        assert second.exit_code == 0, second.output
        # dep_module changed directly; main_module misses too via the chained fingerprint.
        assert _module_names_written(mock_write) == {"dep_module", "main_module"}
