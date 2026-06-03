# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for LOC integration in oops/commands/addons/list.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.addons.list import main
from oops.core.models import AddonInfo
from oops.services.loc import LocStats


def _make_addon_info(
    tmp_path: Path,
    name: str,
    path: str | None = None,
) -> AddonInfo:
    real_path = path or str(tmp_path / name)
    return AddonInfo(
        path=real_path,
        rel_path="",
        technical_name=name,
        symlink=False,
        root=True,
        version="17.0.1.0.0",
        author="Apik",
        maintainers=[],
        summary="",
        external_dependencies={},
        depends=[],
        installable=True,
        submodule="",
        branch="",
        pull_request=False,
        classification="custom",
    )


def _invoke_list_json(tmp_path: Path, addons: list[AddonInfo], loc_map: dict[str, LocStats]) -> list[dict]:
    def _fake_loc(path: str) -> LocStats:
        return loc_map.get(path, LocStats())

    with patch("oops.commands.addons.list.require_repository") as mock_repo, patch(
        "oops.commands.addons.list.list_submodules", return_value={}
    ), patch("oops.commands.addons.list.find_addons", return_value=iter(addons)), patch(
        "oops.commands.addons.list.enrich_addon"
    ), patch("oops.commands.addons.list.get_addon_loc", side_effect=_fake_loc), patch(
        "oops.core.logger.Live", MagicMock()
    ):
        mock_repo.return_value = (MagicMock(), tmp_path)
        result = CliRunner().invoke(main, ["--format", "json"])

    assert result.exit_code == 0, result.output
    return json.loads(result.output)["data"]


class TestListLocKeys:
    def test_row_has_six_loc_keys(self, tmp_path: Path) -> None:
        addon = _make_addon_info(tmp_path, "my_addon")
        loc_map = {addon.path: LocStats(python=100, xml=50, javascript=10, docs=5)}
        rows = _invoke_list_json(tmp_path, [addon], loc_map)

        assert len(rows) == 1
        row = rows[0]
        for key in ("loc_python", "loc_xml", "loc_js", "loc_docs", "loc_total", "loc_pct"):
            assert key in row, f"Missing key: {key}"

    def test_loc_total_equals_sum(self, tmp_path: Path) -> None:
        addon = _make_addon_info(tmp_path, "my_addon")
        loc = LocStats(python=100, xml=50, javascript=10, docs=5)
        loc_map = {addon.path: loc}
        rows = _invoke_list_json(tmp_path, [addon], loc_map)

        row = rows[0]
        assert row["loc_total"] == 165
        assert row["loc_python"] == 100
        assert row["loc_xml"] == 50
        assert row["loc_js"] == 10
        assert row["loc_docs"] == 5

    def test_loc_pct_sums_to_100(self, tmp_path: Path) -> None:
        a1 = _make_addon_info(tmp_path, "addon_a", str(tmp_path / "a"))
        a2 = _make_addon_info(tmp_path, "addon_b", str(tmp_path / "b"))
        loc_map = {
            a1.path: LocStats(python=100, xml=0, javascript=0, docs=0),
            a2.path: LocStats(python=300, xml=0, javascript=0, docs=0),
        }
        rows = _invoke_list_json(tmp_path, [a1, a2], loc_map)

        total_pct = sum(r["loc_pct"] for r in rows)
        assert abs(total_pct - 100.0) < 0.2

    def test_zero_loc_no_divide_by_zero(self, tmp_path: Path) -> None:
        addon = _make_addon_info(tmp_path, "my_addon")
        rows = _invoke_list_json(tmp_path, [addon], {})

        row = rows[0]
        assert row["loc_total"] == 0
        assert row["loc_pct"] == 0.0
