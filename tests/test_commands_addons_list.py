# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for LOC integration in oops/commands/addons/list.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.addons.list import main
from oops.services.loc import _has_cloc, get_addon_loc
from oops_engine.models import Addon, LocStats


def _make_addon_info(
    tmp_path: Path,
    name: str,
    path: str | None = None,
    rel_path: str = "",
    submodule: str = "",
    classification: str = "custom",
) -> Addon:
    real_path = path or str(tmp_path / name)
    return Addon(
        path=real_path,
        rel_path=rel_path,
        technical_name=name,
        symlink=False,
        root=not rel_path,
        version="17.0.1.0.0",
        author="Acme",
        maintainers=[],
        summary="",
        external_dependencies={},
        depends=[],
        installable=True,
        submodule=submodule,
        branch="",
        pull_request=False,
        classification=classification,
    )


def _invoke_list_json(tmp_path: Path, addons: list[Addon], loc_map: dict[str, LocStats]) -> dict:
    def _fake_loc(repo_path: Path, path: str) -> LocStats:  # noqa: ARG001
        return loc_map.get(path, LocStats())

    with patch("oops.commands.addons.list.require_repository") as mock_repo, patch(
        "oops.commands.addons.list.list_submodules", return_value={}
    ), patch("oops_engine.addons.find_addons", return_value=iter(addons)), patch(
        "oops_engine.addons.enrich_addon"
    ), patch("oops.commands.addons.list.get_addon_loc_cached", side_effect=_fake_loc), patch(
        "oops.core.logger.Live", MagicMock()
    ):
        mock_repo.return_value = (MagicMock(), tmp_path)
        result = CliRunner().invoke(main, ["--format", "json"])

    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _addons(payload: dict) -> list[dict]:
    return payload["data"]["addons"]


ADDON_KEYS = {
    "technical_name",
    "path",
    "location",
    "classification",
    "version",
    "installable",
    "summary",
    "author",
    "maintainers",
    "website",
    "depends",
    "external_dependencies",
    "submodule",
    "branch",
    "pull_request",
    "loc",
}


class TestListLocKeys:
    def test_loc_has_six_keys(self, tmp_path: Path) -> None:
        addon = _make_addon_info(tmp_path, "my_addon")
        loc_map = {addon.path: LocStats(python=100, xml=50, javascript=10, docs=5)}
        rows = _addons(_invoke_list_json(tmp_path, [addon], loc_map))

        assert len(rows) == 1
        assert set(rows[0]["loc"]) == {"python", "xml", "javascript", "docs", "total", "pct"}

    def test_loc_total_equals_sum(self, tmp_path: Path) -> None:
        addon = _make_addon_info(tmp_path, "my_addon")
        loc_map = {addon.path: LocStats(python=100, xml=50, javascript=10, docs=5)}
        loc = _addons(_invoke_list_json(tmp_path, [addon], loc_map))[0]["loc"]

        assert loc["total"] == 165
        assert loc["python"] == 100
        assert loc["xml"] == 50
        assert loc["javascript"] == 10
        assert loc["docs"] == 5

    def test_loc_pct_sums_to_100(self, tmp_path: Path) -> None:
        a1 = _make_addon_info(tmp_path, "addon_a", str(tmp_path / "a"))
        a2 = _make_addon_info(tmp_path, "addon_b", str(tmp_path / "b"))
        loc_map = {
            a1.path: LocStats(python=100, xml=0, javascript=0, docs=0),
            a2.path: LocStats(python=300, xml=0, javascript=0, docs=0),
        }
        rows = _addons(_invoke_list_json(tmp_path, [a1, a2], loc_map))

        total_pct = sum(r["loc"]["pct"] for r in rows)
        assert abs(total_pct - 100.0) < 0.2

    def test_zero_loc_no_divide_by_zero(self, tmp_path: Path) -> None:
        addon = _make_addon_info(tmp_path, "my_addon")
        loc = _addons(_invoke_list_json(tmp_path, [addon], {}))[0]["loc"]

        assert loc["total"] == 0
        assert loc["pct"] == 0.0


class TestListContract:
    def test_envelope_keys(self, tmp_path: Path) -> None:
        payload = _invoke_list_json(tmp_path, [_make_addon_info(tmp_path, "my_addon")], {})

        assert set(payload) == {"data", "warnings", "errors", "metadata"}
        assert set(payload["data"]) == {"summary", "addons"}

    def test_addon_key_set(self, tmp_path: Path) -> None:
        rows = _addons(_invoke_list_json(tmp_path, [_make_addon_info(tmp_path, "my_addon")], {}))

        assert set(rows[0]) == ADDON_KEYS

    def test_summary_counters_always_have_all_keys(self, tmp_path: Path) -> None:
        addon = _make_addon_info(tmp_path, "my_addon", classification="oca")
        loc_map = {addon.path: LocStats(python=7, xml=3)}
        summary = _invoke_list_json(tmp_path, [addon], loc_map)["data"]["summary"]

        assert summary["total"] == 1
        assert summary["by_location"] == {"active": 0, "local": 1, "inactive": 0}
        assert summary["by_classification"] == {"custom": 0, "oca": 1, "third-party": 0}
        assert summary["loc"] == {"python": 7, "xml": 3, "javascript": 0, "docs": 0, "total": 10}

    def test_empty_submodule_and_branch_become_null(self, tmp_path: Path) -> None:
        row = _addons(_invoke_list_json(tmp_path, [_make_addon_info(tmp_path, "my_addon")], {}))[0]

        assert row["submodule"] is None
        assert row["branch"] is None
        assert row["pull_request"] is False

    def test_path_at_root(self, tmp_path: Path) -> None:
        row = _addons(_invoke_list_json(tmp_path, [_make_addon_info(tmp_path, "my_addon")], {}))[0]

        assert row["path"] == "my_addon"
        assert row["location"] == "local"

    def test_path_in_submodule(self, tmp_path: Path) -> None:
        addon = _make_addon_info(
            tmp_path, "my_addon", rel_path=".third-party/OCA/x", submodule="OCA/x"
        )
        row = _addons(_invoke_list_json(tmp_path, [addon], {}))[0]

        assert row["path"] == ".third-party/OCA/x/my_addon"
        assert row["location"] == "inactive"
        assert row["submodule"] == "OCA/x"


class TestListLocCaching:
    """Exercises the real get_addon_loc_cached() path end-to-end (not mocked)
    — only the cloc subprocess wrapper (oops_engine.loc.run) is faked."""

    def test_second_invocation_reuses_persisted_loc_cache(self, tmp_path: Path) -> None:
        addon_dir = tmp_path / "my_addon"
        addon_dir.mkdir()
        (addon_dir / "__manifest__.py").write_text("{}", encoding="utf-8")
        addon = _make_addon_info(tmp_path, "my_addon", str(addon_dir))

        calls = {"n": 0}

        def _run(*a, **k):  # noqa: ANN002, ANN003
            calls["n"] += 1
            return json.dumps({"Python": {"code": 10}})

        get_addon_loc.cache_clear()
        _has_cloc.cache_clear()
        try:
            with patch("oops.commands.addons.list.require_repository") as mock_repo, patch(
                "oops.commands.addons.list.list_submodules", return_value={}
            ), patch("oops_engine.addons.find_addons", return_value=iter([addon])), patch(
                "oops_engine.addons.enrich_addon"
            ), patch("shutil.which", lambda _: "/usr/bin/cloc"), patch("oops_engine.loc.run", side_effect=_run), patch(
                "oops.core.logger.Live", MagicMock()
            ):
                mock_repo.return_value = (MagicMock(), tmp_path)
                first = CliRunner().invoke(main, ["--format", "json"])
                get_addon_loc.cache_clear()  # defeat the in-process cache; only the persisted one should hit
                second = CliRunner().invoke(main, ["--format", "json"])
        finally:
            get_addon_loc.cache_clear()
            _has_cloc.cache_clear()

        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        assert calls["n"] == 1  # cloc shelled out only once across both invocations
        assert (tmp_path / ".oops-cache" / "kb.db").exists()

    def test_loc_cache_is_not_shared_across_repos(self, tmp_path: Path) -> None:
        """Two different repos, each with an addon of identical content (same
        fingerprint), must not share a cached LOC entry — each repo's cache
        lives in its own `.oops-cache/kb.db`, keyed by that repo's repo_id."""
        from oops_engine.loc import get_addon_loc_cached

        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        for repo in (repo_a, repo_b):
            addon_dir = repo / "my_addon"
            addon_dir.mkdir(parents=True)
            (addon_dir / "__manifest__.py").write_text("{}", encoding="utf-8")

        calls: list[str] = []

        def _run(cmd, **_k):  # noqa: ANN001, ANN003
            calls.append(cmd[-1])  # addon path is the last cloc arg
            return json.dumps({"Python": {"code": 10}})

        get_addon_loc.cache_clear()
        _has_cloc.cache_clear()
        try:
            with patch("shutil.which", lambda _: "/usr/bin/cloc"), \
                    patch("oops_engine.loc.run", side_effect=_run):
                loc_a = get_addon_loc_cached(repo_a, str(repo_a / "my_addon"))
                get_addon_loc.cache_clear()  # defeat the in-process cache only
                loc_b = get_addon_loc_cached(repo_b, str(repo_b / "my_addon"))
        finally:
            get_addon_loc.cache_clear()
            _has_cloc.cache_clear()

        assert loc_a.python == 10
        assert loc_b.python == 10
        assert len(calls) == 2  # cloc shelled out once per repo — no cross-repo cache hit
        assert (repo_a / ".oops-cache" / "kb.db").exists()
        assert (repo_b / ".oops-cache" / "kb.db").exists()

    def test_no_prebuilt_kb_required(self, tmp_path: Path) -> None:
        """`oops addons list` must work on a project with no `.oops-cache/kb.db`
        yet — it must not require a prior `oops addons analyze`/build-kb run."""
        addon_dir = tmp_path / "my_addon"
        addon_dir.mkdir()
        (addon_dir / "__manifest__.py").write_text("{}", encoding="utf-8")
        addon = _make_addon_info(tmp_path, "my_addon", str(addon_dir))

        assert not (tmp_path / ".oops-cache" / "kb.db").exists()

        get_addon_loc.cache_clear()
        _has_cloc.cache_clear()
        try:
            with patch("oops.commands.addons.list.require_repository") as mock_repo, patch(
                "oops.commands.addons.list.list_submodules", return_value={}
            ), patch("oops_engine.addons.find_addons", return_value=iter([addon])), patch(
                "oops_engine.addons.enrich_addon"
            ), patch("shutil.which", lambda _: None), patch("oops.core.logger.Live", MagicMock()):
                mock_repo.return_value = (MagicMock(), tmp_path)
                result = CliRunner().invoke(main, ["--format", "json"])
        finally:
            get_addon_loc.cache_clear()
            _has_cloc.cache_clear()

        assert result.exit_code == 0, result.output
