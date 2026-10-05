# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""CLI smoke tests for `oops project show --format json`."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.project.show import main
from oops.core.models import ImageInfo


def _image() -> ImageInfo:
    return ImageInfo(
        image="acme/odoo:15.0-20230103",
        registry="acme",
        repository="odoo",
        major_version=15.0,
        release=date(2023, 1, 3),
        enterprise=False,
    )


def _invoke(tmp_path: Path, parse_side_effect=None) -> dict:  # noqa: ANN001
    repo = MagicMock()
    repo.remote.return_value.url = "git@github.com:org/my_project.git"
    repo.active_branch.name = "main"

    with patch("oops.commands.project.show.require_repository", return_value=(repo, tmp_path)), patch(
        "oops.commands.project.show.parse_odoo_version",
        return_value=_image(),
        side_effect=parse_side_effect,
    ), patch("oops.commands.project.show.get_image_updates", return_value=[]), patch(
        "oops.commands.project.show.get_last_release", return_value="v1.0.0"
    ), patch(
        "oops.commands.project.show.get_next_releases", return_value=("v1.1.0", "v1.0.1", "v2.0.0")
    ), patch("oops.commands.project.show.get_last_commit", return_value=None), patch(
        "oops.core.logger.Live", MagicMock()
    ):
        result = CliRunner().invoke(main, ["--format", "json"], env={"TOKEN": "", "GH_TOKEN": "", "GITHUB_TOKEN": ""})

    assert result.exit_code == 0, result.output
    return json.loads(result.output)


class TestProjectShowJson:
    def test_envelope(self, tmp_path: Path) -> None:
        payload = _invoke(tmp_path)

        assert set(payload) == {"data", "warnings", "errors", "metadata"}
        assert set(payload["data"]) == {"project", "odoo", "git", "ci"}
        assert payload["errors"] == []
        assert payload["data"]["project"] == tmp_path.name
        assert payload["data"]["odoo"]["version"] == "15.0"
        assert payload["data"]["odoo"]["updates"]["available"] == 0
        assert payload["data"]["git"]["branch"] == "main"
        assert payload["data"]["git"]["next_releases"] == {"fix": "v1.0.1", "minor": "v1.1.0", "major": "v2.0.0"}
        assert payload["data"]["ci"] is None

    def test_missing_version_file(self, tmp_path: Path) -> None:
        payload = _invoke(tmp_path, parse_side_effect=FileNotFoundError("odoo_version.txt not found"))

        assert payload["data"]["odoo"] == {"version": None, "edition": None, "image": None, "updates": None}
        assert payload["errors"] == ["odoo_version.txt not found"]
