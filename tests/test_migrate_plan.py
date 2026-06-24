# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops migrate plan command."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner
from oops.commands.migrate.common import (
    ModulePlan,
    ModuleState,
    Origin,
    Plan,
    State,
    _guess_action,
    _needs_review,
    load_plan,
    save_plan,
    save_state,
)
from oops.commands.migrate.plan import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_state(repo_path: Path, from_v="18.0", to_v="19.0", modules=None) -> Path:
    """Write a minimal state.yml under repo_path."""
    state_path = repo_path / ".oops" / "migrate" / "state.yml"
    state = State(
        version=2,
        source_ref=from_v,
        from_version=from_v,
        to_version=to_v,
        modules=modules or {
            "custom_sale": ModuleState(
                name="custom_sale",
                origin=Origin(kind="custom"),
                depends_on=["sale"],
            ),
            "oca_partner": ModuleState(
                name="oca_partner",
                origin=Origin(kind="oca", repo="OCA/partner-contact"),
                depends_on=["base"],
                upstream_available=True,
            ),
        },
    )
    save_state(state_path, state)
    return state_path


@contextmanager
def _mock_repo(repo_path):
    mock_repo = MagicMock()
    mock_repo.active_branch.name = "18.0"
    with patch("oops.commands.migrate.plan.require_repository", return_value=(mock_repo, repo_path)):
        yield


# ---------------------------------------------------------------------------
# Unit tests — _guess_action
# ---------------------------------------------------------------------------


class TestGuessAction:
    def _ms(self, kind, upstream_available=None, upstream_prs=None):
        origin = Origin(kind=kind)
        return ModuleState(
            name="x",
            origin=origin,
            upstream_available=upstream_available,
            upstream_prs=upstream_prs or [],
        )

    def test_custom_always_port(self):
        assert _guess_action(self._ms("custom")) == "port"

    def test_oca_available_pull(self):
        assert _guess_action(self._ms("oca", upstream_available=True)) == "pull"

    def test_oca_absent_no_pr_port(self):
        assert _guess_action(self._ms("oca", upstream_available=False)) == "port"

    def test_oca_absent_with_pr_still_port(self):
        assert _guess_action(self._ms("oca", upstream_available=False, upstream_prs=["url"])) == "port"

    def test_oca_not_probed_port(self):
        assert _guess_action(self._ms("oca", upstream_available=None)) == "port"

    def test_third_party_port(self):
        assert _guess_action(self._ms("third-party")) == "port"


# ---------------------------------------------------------------------------
# Unit tests — _needs_review
# ---------------------------------------------------------------------------


class TestNeedsReview:
    def _ms(self, kind, upstream_available=None, upstream_prs=None):
        origin = Origin(kind=kind)
        return ModuleState(
            name="x",
            origin=origin,
            upstream_available=upstream_available,
            upstream_prs=upstream_prs or [],
        )

    def test_custom_no_review(self):
        assert _needs_review(self._ms("custom"), "port") is False

    def test_oca_available_no_review(self):
        assert _needs_review(self._ms("oca", upstream_available=True), "pull") is False

    def test_oca_not_probed_review(self):
        assert _needs_review(self._ms("oca", upstream_available=None), "port") is True

    def test_oca_absent_with_pr_review(self):
        assert _needs_review(self._ms("oca", upstream_available=False, upstream_prs=["url"]), "port") is True


# ---------------------------------------------------------------------------
# Round-trip tests — load_plan / save_plan
# ---------------------------------------------------------------------------


def test_save_load_plan_roundtrip(tmp_path):
    plan = Plan(
        version=2,
        migration={"from": "18.0", "to": "19.0"},
        modules={
            "my_addon": ModulePlan(
                name="my_addon",
                action="port",
                origin=Origin(kind="custom"),
                depends_on=["base"],
                review=False,
            ),
            "oca_mod": ModulePlan(
                name="oca_mod",
                action="pull",
                origin=Origin(kind="oca", repo="OCA/some-repo"),
                depends_on=[],
                review=True,
                group="phase-1",
            ),
        },
    )
    path = tmp_path / ".oops" / "migrate" / "plan.yml"
    save_plan(path, plan)
    assert path.exists()

    loaded = load_plan(path)
    assert loaded.version == 2
    assert loaded.migration["from"] == "18.0"
    assert loaded.modules["my_addon"].action == "port"
    assert loaded.modules["my_addon"].origin.kind == "custom"
    assert loaded.modules["my_addon"].review is False
    assert loaded.modules["oca_mod"].group == "phase-1"
    assert loaded.modules["oca_mod"].review is True


def test_save_plan_omits_none_fields(tmp_path):
    plan = Plan(
        version=2,
        migration={},
        modules={
            "x": ModulePlan(name="x", action="keep", origin=Origin(kind="custom")),
        },
    )
    path = tmp_path / "plan.yml"
    save_plan(path, plan)
    raw = yaml.safe_load(path.read_text())
    assert "review" not in raw["modules"]["x"]
    for key in ("group", "tools", "merge_with", "rename", "priority", "reason"):
        assert key not in raw["modules"]["x"]


# ---------------------------------------------------------------------------
# Integration tests — command behavior
# ---------------------------------------------------------------------------


def test_plan_first_run_writes_plan(tmp_path):
    _write_state(tmp_path)
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, [])
    assert result.exit_code == 0, result.output
    plan_file = tmp_path / ".oops" / "migrate" / "plan.yml"
    assert plan_file.exists()


def test_plan_seeds_correct_actions(tmp_path):
    _write_state(tmp_path)
    with _mock_repo(tmp_path):
        CliRunner().invoke(main, [])
    data = yaml.safe_load((tmp_path / ".oops" / "migrate" / "plan.yml").read_text())
    assert data["modules"]["custom_sale"]["action"] == "port"
    assert "review" not in data["modules"]["custom_sale"]
    assert data["modules"]["oca_partner"]["action"] == "pull"
    assert "review" not in data["modules"]["oca_partner"]


def test_plan_refuses_without_state(tmp_path):
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, [])
    assert result.exit_code == 1
    assert "analyze" in result.output.lower()


def test_plan_reconcile_preserves_human_action(tmp_path):
    _write_state(tmp_path)
    with _mock_repo(tmp_path):
        CliRunner().invoke(main, [])

    plan_path = tmp_path / ".oops" / "migrate" / "plan.yml"
    data = yaml.safe_load(plan_path.read_text())
    data["modules"]["oca_partner"]["action"] = "drop"
    plan_path.write_text(yaml.safe_dump(data))

    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, [])
    assert result.exit_code == 0, result.output

    data2 = yaml.safe_load(plan_path.read_text())
    assert data2["modules"]["oca_partner"]["action"] == "drop"


def test_plan_flags_disappeared_module(tmp_path):
    _write_state(tmp_path)
    with _mock_repo(tmp_path):
        CliRunner().invoke(main, [])

    _write_state(tmp_path, modules={
        "custom_sale": ModuleState(
            name="custom_sale",
            origin=Origin(kind="custom"),
            depends_on=[],
        ),
    })

    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, [])
    assert result.exit_code == 0, result.output

    data = yaml.safe_load((tmp_path / ".oops" / "migrate" / "plan.yml").read_text())
    assert "oca_partner" in data["modules"]
    assert data["modules"]["oca_partner"]["review"] is True


def test_plan_format_json(tmp_path):
    _write_state(tmp_path)
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, ["--format", "json"])
    assert result.exit_code == 0, result.output
    # Strip any spinner/progress prefix before the JSON object.
    json_start = result.output.find("{")
    payload = json.loads(result.output[json_start:])
    assert "modules" in payload
    assert "metrics" in payload
