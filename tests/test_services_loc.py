# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

import json
import subprocess
import time

import pytest
from oops.services.loc import _has_cloc, get_addon_loc, get_addon_loc_cached
from oops_engine.loc import _has_cloc as _engine_has_cloc
from oops_engine.loc import get_addon_loc as _engine_get_addon_loc
from oops_engine.loc import get_addon_loc_cached as _engine_get_addon_loc_cached
from oops_engine.models import LocStats


def test_services_loc_reexports_are_the_engine_implementation() -> None:
    """`oops.services.loc` is a thin back-compat re-export of `oops_engine.loc`."""
    assert get_addon_loc is _engine_get_addon_loc
    assert get_addon_loc_cached is _engine_get_addon_loc_cached
    assert _has_cloc is _engine_has_cloc


@pytest.fixture(autouse=True)
def _clear_caches():
    get_addon_loc.cache_clear()
    _has_cloc.cache_clear()
    yield
    get_addon_loc.cache_clear()
    _has_cloc.cache_clear()


SAMPLE_CLOC = json.dumps(
    {
        "header": {"cloc_version": "2.08"},
        "Python": {"nFiles": 3, "blank": 50, "comment": 20, "code": 300},
        "XML": {"nFiles": 2, "blank": 10, "comment": 5, "code": 150},
        "JavaScript": {"nFiles": 1, "blank": 5, "comment": 1, "code": 80},
        "Markdown": {"nFiles": 1, "blank": 5, "comment": 0, "code": 40},
        "reStructuredText": {"nFiles": 1, "blank": 3, "comment": 0, "code": 25},
        "SUM": {"blank": 73, "comment": 26, "code": 595, "nFiles": 8},
    }
)


def test_get_addon_loc_parses_languages(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    monkeypatch.setattr("oops_engine.loc.run", lambda *a, **k: SAMPLE_CLOC)

    stats = get_addon_loc("/fake/addon")

    assert stats == LocStats(python=300, xml=150, javascript=80, docs=65)
    assert stats.total == 595


def test_get_addon_loc_missing_binary(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    stats = get_addon_loc("/fake/addon")
    assert stats == LocStats()


def test_get_addon_loc_decode_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    monkeypatch.setattr("oops_engine.loc.run", lambda *a, **k: "not-json")
    assert get_addon_loc("/fake/addon") == LocStats()


def test_get_addon_loc_subprocess_failure(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")

    def _boom(*a, **k):
        raise subprocess.CalledProcessError(1, "cloc")

    monkeypatch.setattr("oops_engine.loc.run", _boom)
    assert get_addon_loc("/fake/addon") == LocStats()


def test_loc_stats_total():
    stats = LocStats(python=100, xml=50, javascript=30, docs=20)
    assert stats.total == 200


def test_get_addon_loc_is_cached(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    calls = {"n": 0}

    def _run(*a, **k):
        calls["n"] += 1
        return SAMPLE_CLOC

    monkeypatch.setattr("oops_engine.loc.run", _run)
    get_addon_loc("/fake/addon")
    get_addon_loc("/fake/addon")
    assert calls["n"] == 1


def test_get_addon_loc_empty_output(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    monkeypatch.setattr("oops_engine.loc.run", lambda *a, **k: "")
    assert get_addon_loc("/fake/addon") == LocStats()


# ---------------------------------------------------------------------------
# get_addon_loc_cached — persistent, content-fingerprint-keyed LOC cache
# ---------------------------------------------------------------------------


def test_get_addon_loc_cached_creates_kb_file_if_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    monkeypatch.setattr("oops_engine.loc.run", lambda *a, **k: SAMPLE_CLOC)

    repo_path = tmp_path / "repo"
    addon_path = repo_path / "my_addon"
    addon_path.mkdir(parents=True)
    (addon_path / "__manifest__.py").write_text("{}", encoding="utf-8")

    kb_path = repo_path / ".oops-cache" / "kb.db"
    assert not kb_path.exists()

    stats = get_addon_loc_cached(repo_path, str(addon_path))

    assert stats == LocStats(python=300, xml=150, javascript=80, docs=65)
    assert kb_path.exists()


def test_get_addon_loc_cached_hits_cache_on_unchanged_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    calls = {"n": 0}

    def _run(*a, **k):
        calls["n"] += 1
        return SAMPLE_CLOC

    monkeypatch.setattr("oops_engine.loc.run", _run)

    repo_path = tmp_path / "repo"
    addon_path = repo_path / "my_addon"
    addon_path.mkdir(parents=True)
    (addon_path / "__manifest__.py").write_text("{}", encoding="utf-8")

    first = get_addon_loc_cached(repo_path, str(addon_path))
    get_addon_loc.cache_clear()  # defeat the in-process lru_cache — prove the persisted cache is what's hit
    second = get_addon_loc_cached(repo_path, str(addon_path))

    assert first == second
    assert calls["n"] == 1  # cloc only shelled out once


def test_get_addon_loc_cached_misses_and_repopulates_after_edit(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    calls = {"n": 0}

    def _run(*a, **k):
        calls["n"] += 1
        return SAMPLE_CLOC

    monkeypatch.setattr("oops_engine.loc.run", _run)

    repo_path = tmp_path / "repo"
    addon_path = repo_path / "my_addon"
    addon_path.mkdir(parents=True)
    (addon_path / "__manifest__.py").write_text("{}", encoding="utf-8")

    get_addon_loc_cached(repo_path, str(addon_path))
    get_addon_loc.cache_clear()

    time.sleep(0.01)
    (addon_path / "extra.py").write_text("x = 1", encoding="utf-8")

    result = get_addon_loc_cached(repo_path, str(addon_path))

    assert calls["n"] == 2  # content changed -> fingerprint miss -> cloc reran
    assert result == LocStats(python=300, xml=150, javascript=80, docs=65)
