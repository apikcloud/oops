# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_analyze_run_analysis.py — tests/test_analyze_run_analysis.py

"""Direct tests of run_analysis(), independent of the Click command wrapper.

Locks in the extracted-function contract that `project_pipeline.build_ir()`
(and the `--all` flag) build on.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from oops.commands.addons.analyze import run_analysis
from oops.core.models import ModuleSummary

from .test_analyze import NEW_MODEL_SOURCE, _make_kb, _make_module_full, _mock_analyze


class TestRunAnalysis:
    def test_returns_result_collection_with_installed_and_load_order(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "version": "17.0.1.0.0", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )

        with _mock_analyze(tmp_path, db_path):
            run = run_analysis(MagicMock(), tmp_path, [module_path], refresh=False)

        assert run.results.ok
        assert len(run.results.items) == 1
        summary = run.results.items[0].unwrap
        assert isinstance(summary, ModuleSummary)
        assert summary.module_name == "my_module"
        # installed/load_order feed AnalyzePresenter without callers re-deriving them.
        assert run.installed is None or isinstance(run.installed, set)
        assert isinstance(run.load_order, dict)

    def test_multiple_modules_all_analysed(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        m1 = _make_module_full(tmp_path, "mod_alpha", manifest={"name": "Alpha", "depends": ["base"]})
        m2 = _make_module_full(tmp_path, "mod_beta", manifest={"name": "Beta", "depends": ["base"]})

        with _mock_analyze(tmp_path, db_path):
            run = run_analysis(MagicMock(), tmp_path, [m1, m2], refresh=False)

        names = {r.unwrap.module_name for r in run.results.items}
        assert names == {"mod_alpha", "mod_beta"}

    def test_no_cache_forces_reanalysis(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kb.db"
        _make_kb(db_path)
        module_path = _make_module_full(
            tmp_path,
            "my_module",
            manifest={"name": "My Module", "depends": ["base"]},
            models={"my_model.py": NEW_MODEL_SOURCE},
        )

        with _mock_analyze(tmp_path, db_path):
            run_analysis(MagicMock(), tmp_path, [module_path], refresh=False)

        with _mock_analyze(tmp_path, db_path):
            run = run_analysis(MagicMock(), tmp_path, [module_path], refresh=False, no_cache=True)

        assert run.results.ok
        assert run.results.items[0].unwrap.module_name == "my_module"
