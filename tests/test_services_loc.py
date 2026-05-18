# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

import json
import subprocess

import pytest
from oops.services.loc import LocStats, _has_cloc, get_addon_loc


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
    monkeypatch.setattr("oops.services.loc.run", lambda *a, **k: SAMPLE_CLOC)

    stats = get_addon_loc("/fake/addon")

    assert stats == LocStats(python=300, xml=150, javascript=80, docs=65)
    assert stats.total == 595


def test_get_addon_loc_missing_binary(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    stats = get_addon_loc("/fake/addon")
    assert stats == LocStats()


def test_get_addon_loc_decode_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    monkeypatch.setattr("oops.services.loc.run", lambda *a, **k: "not-json")
    assert get_addon_loc("/fake/addon") == LocStats()


def test_get_addon_loc_subprocess_failure(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")

    def _boom(*a, **k):
        raise subprocess.CalledProcessError(1, "cloc")

    monkeypatch.setattr("oops.services.loc.run", _boom)
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

    monkeypatch.setattr("oops.services.loc.run", _run)
    get_addon_loc("/fake/addon")
    get_addon_loc("/fake/addon")
    assert calls["n"] == 1


def test_get_addon_loc_empty_output(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/cloc")
    monkeypatch.setattr("oops.services.loc.run", lambda *a, **k: "")
    assert get_addon_loc("/fake/addon") == LocStats()
