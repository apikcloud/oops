# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops migrate analyze command."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner
from oops.commands.migrate.analyze import main
from oops.commands.migrate.common import (
    ModuleState,
    Origin,
    State,
    classify_origin,
    load_state,
    save_state,
)
from oops.utils.net import website_to_github_repo

# ---------------------------------------------------------------------------
# website_to_github_repo
# ---------------------------------------------------------------------------


class TestWebsiteToGithubRepo:
    def test_oca_url(self):
        assert website_to_github_repo("https://github.com/OCA/multi-company") == ("OCA", "multi-company")

    def test_lowercase_oca(self):
        assert website_to_github_repo("https://github.com/oca/server-tools") == ("OCA", "server-tools")

    def test_non_github(self):
        assert website_to_github_repo("https://odoo.com") is None

    def test_empty(self):
        assert website_to_github_repo(None) is None
        assert website_to_github_repo("") is None

    def test_non_oca_github(self):
        pair = website_to_github_repo("https://github.com/apikcloud/some-repo")
        assert pair == ("apikcloud", "some-repo")


# ---------------------------------------------------------------------------
# classify_origin
# ---------------------------------------------------------------------------


class TestClassifyOrigin:
    def _make_addon(self, classification, submodule="", website=None):
        addon = MagicMock()
        addon.classification = classification
        addon.submodule = submodule
        addon.website = website
        addon.branch = "18.0"
        return addon

    def test_oca_via_submodule(self):
        addon = self._make_addon("oca", submodule="OCA/server-tools")
        assert classify_origin(addon) == ("oca", "OCA/server-tools")

    def test_oca_via_website_no_submodule(self):
        addon = self._make_addon("third-party", website="https://github.com/OCA/multi-company")
        kind, slug = classify_origin(addon)
        assert kind == "third-party"
        assert slug == "OCA/multi-company"

    def test_local_custom(self):
        addon = self._make_addon("custom")
        assert classify_origin(addon) == ("custom", None)

    def test_third_party_submodule(self):
        addon = self._make_addon("third-party", submodule="some-vendor/some-repo")
        assert classify_origin(addon) == ("third-party", "some-vendor/some-repo")


# ---------------------------------------------------------------------------
# save_state / load_state round-trip
# ---------------------------------------------------------------------------


def test_save_load_state_roundtrip(tmp_path):
    state = State(
        version=2,
        source_ref="18.0",
        from_version="18.0",
        to_version="19.0",
        modules={
            "my_module": ModuleState(
                name="my_module",
                origin=Origin(kind="custom"),
                depends_on=["base"],
            ),
            "oca_mod": ModuleState(
                name="oca_mod",
                origin=Origin(kind="oca", repo="OCA/server-tools"),
            ),
        },
    )
    path = tmp_path / ".oops" / "migrate" / "state.yml"
    save_state(path, state)
    assert path.exists()
    loaded = load_state(path)
    assert loaded.from_version == "18.0"
    assert loaded.to_version == "19.0"
    assert loaded.modules["my_module"].origin.kind == "custom"
    assert loaded.modules["oca_mod"].origin.kind == "oca"


# ---------------------------------------------------------------------------
# Command integration tests
# ---------------------------------------------------------------------------


def _make_addon_dir(base: Path, name: str, author: str = "Acme", depends=None, website=None):
    d = base / name
    d.mkdir(parents=True)
    manifest = {"name": name, "author": author, "depends": depends or ["base"]}
    if website:
        manifest["website"] = website
    (d / "__manifest__.py").write_text(repr(manifest))
    return d


@contextmanager
def _mock_repo(repo_path):
    mock_repo = MagicMock()
    mock_repo.active_branch.name = "18.0"
    with patch("oops.commands.migrate.analyze.require_repository", return_value=(mock_repo, repo_path)):
        with patch("oops.commands.migrate.analyze.list_submodules", return_value={}):
            yield


def test_analyze_writes_state(tmp_path):
    _make_addon_dir(tmp_path, "custom_sale", author="Acme")
    _make_addon_dir(tmp_path, "oca_partner", author="Odoo Community Association (OCA)", website="https://github.com/OCA/partner-contact")

    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, ["--from", "18.0", "--to", "19.0", "--no-probe-upstream"])

    assert result.exit_code == 0, result.output
    state_file = tmp_path / ".oops" / "migrate" / "state.yml"
    assert state_file.exists()

    data = yaml.safe_load(state_file.read_text())
    assert data["from_version"] == "18.0"
    assert data["to_version"] == "19.0"
    assert "custom_sale" in data["modules"]
    assert "oca_partner" in data["modules"]
    assert data["modules"]["oca_partner"]["origin"]["kind"] == "oca"
    assert data["modules"]["oca_partner"]["origin"]["repo"] == "OCA/partner-contact"
    assert data["modules"]["custom_sale"]["origin"]["kind"] == "custom"


def test_analyze_requires_to_version(tmp_path):
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, ["--from", "18.0", "--no-probe-upstream"])
    assert result.exit_code == 1
    assert "to" in result.output.lower() or "version" in result.output.lower()


def test_analyze_detects_from_version_from_branch(tmp_path):
    """When --from is omitted, from_version is derived from branch name."""
    _make_addon_dir(tmp_path, "my_mod")
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, ["--to", "19.0", "--no-probe-upstream"])
    assert result.exit_code == 0, result.output
    state_file = tmp_path / ".oops" / "migrate" / "state.yml"
    data = yaml.safe_load(state_file.read_text())
    assert data["from_version"] == "18.0"


def test_analyze_json_format(tmp_path):
    _make_addon_dir(tmp_path, "my_mod")
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, ["--from", "18.0", "--to", "19.0", "--no-probe-upstream", "--format", "json"])
    assert result.exit_code == 0, result.output
    import json
    json_start = result.output.index("{")
    data = json.loads(result.output[json_start:])
    assert "metrics" in data
    assert "modules" in data


def test_analyze_probe_upstream_default_on(tmp_path):
    """--probe-upstream is on by default; check_upstream_module is called for oca modules."""
    _make_addon_dir(tmp_path, "oca_mod", author="Odoo Community Association (OCA)", website="https://github.com/OCA/server-tools")

    with _mock_repo(tmp_path):
        with patch(
            "oops.commands.migrate.analyze._probe_modules",
        ) as mock_probe:
            CliRunner().invoke(main, ["--from", "18.0", "--to", "19.0"])

    mock_probe.assert_called_once()


def test_analyze_no_probe_upstream_skips_probe(tmp_path):
    """--no-probe-upstream prevents any API calls."""
    _make_addon_dir(tmp_path, "oca_mod", author="Odoo Community Association (OCA)")

    with _mock_repo(tmp_path):
        with patch(
            "oops.commands.migrate.analyze._probe_modules",
        ) as mock_probe:
            CliRunner().invoke(main, ["--from", "18.0", "--to", "19.0", "--no-probe-upstream"])

    mock_probe.assert_not_called()


def test_analyze_html_format(tmp_path):
    _make_addon_dir(tmp_path, "my_mod")
    out = tmp_path / "report.html"
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(
            main,
            ["--from", "18.0", "--to", "19.0", "--no-probe-upstream", "--format", "html", "--output-path", str(out)],
        )
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0
    content = out.read_text()
    assert "window.OOPS" in content
    assert '"migrate analyze"' in content


def test_analyze_unknown_format_rejected(tmp_path):
    _make_addon_dir(tmp_path, "my_mod")
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, ["--from", "18.0", "--to", "19.0", "--format", "bogus"])
    assert result.exit_code != 0
