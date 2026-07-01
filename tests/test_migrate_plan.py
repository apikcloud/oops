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
    MigrationPlan,
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
from oops.commands.migrate.plan import _enrich_ghost_modules, _insert_ghost_modules, main

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

    def test_oca_absent_with_pr_pull(self):
        # PR exists → treat as pull (not yet merged, review=True flags it)
        assert _guess_action(self._ms("oca", upstream_available=False, upstream_prs=["url"])) == "pull"

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
    for key in ("group", "tools", "merge_with", "rename", "priority", "reason", "pr"):
        assert key not in raw["modules"]["x"]


def test_manual_pr_roundtrip(tmp_path):
    plan = Plan(
        version=2,
        migration={},
        modules={
            "oca_mod": ModulePlan(
                name="oca_mod",
                action="pull",
                origin=Origin(kind="oca", repo="OCA/bank-payment"),
                pr="https://github.com/OCA/bank-payment/pull/42",
            ),
        },
    )
    path = tmp_path / "plan.yml"
    save_plan(path, plan)
    raw = yaml.safe_load(path.read_text())
    assert raw["modules"]["oca_mod"]["pr"] == "https://github.com/OCA/bank-payment/pull/42"

    loaded = load_plan(path)
    assert loaded.modules["oca_mod"].pr == "https://github.com/OCA/bank-payment/pull/42"


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


def test_plan_seed_migration_keys(tmp_path):
    _write_state(tmp_path, from_v="18.0", to_v="19.0")
    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, [])
    assert result.exit_code == 0, result.output
    data = yaml.safe_load((tmp_path / ".oops" / "migrate" / "plan.yml").read_text())
    mig = data["migration"]
    assert mig["dest_branch"] == "main"
    assert mig["branch_template"] == "mig/19.0/{module}"
    assert "target_branch" not in mig
    assert "strategy" not in mig


def test_plan_reconcile_backfills_dest_branch(tmp_path):
    plan_path = tmp_path / ".oops" / "migrate" / "plan.yml"
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    # Write an old-style plan with target_branch template and no dest_branch.
    old_plan = {
        "version": 2,
        "migration": {
            "from": "18.0",
            "to": "19.0",
            "source_ref": "18.0",
            "target_branch": "mig/19.0/{module}",
            "branch_template": "mig/19.0/{module}",
        },
        "modules": {
            "custom_sale": {"action": "port", "origin": {"kind": "custom"}},
            "oca_partner": {"action": "pull", "origin": {"kind": "oca", "repo": "OCA/partner-contact"}},
        },
    }
    plan_path.write_text(yaml.safe_dump(old_plan))
    _write_state(tmp_path)

    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, [])
    assert result.exit_code == 0, result.output

    data = yaml.safe_load(plan_path.read_text())
    mig = data["migration"]
    assert mig["dest_branch"] == "main"
    assert "target_branch" not in mig


def test_plan_reconcile_preserves_explicit_dest_branch(tmp_path):
    plan_path = tmp_path / ".oops" / "migrate" / "plan.yml"
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    old_plan = {
        "version": 2,
        "migration": {
            "from": "18.0",
            "to": "19.0",
            "source_ref": "18.0",
            "dest_branch": "18.0",
            "branch_template": "mig/19.0/{module}",
        },
        "modules": {
            "custom_sale": {"action": "port", "origin": {"kind": "custom"}},
            "oca_partner": {"action": "pull", "origin": {"kind": "oca", "repo": "OCA/partner-contact"}},
        },
    }
    plan_path.write_text(yaml.safe_dump(old_plan))
    _write_state(tmp_path)

    with _mock_repo(tmp_path):
        result = CliRunner().invoke(main, [])
    assert result.exit_code == 0, result.output

    data = yaml.safe_load(plan_path.read_text())
    assert data["migration"]["dest_branch"] == "18.0"


# ---------------------------------------------------------------------------
# Unit tests — _insert_ghost_modules
# ---------------------------------------------------------------------------


def _make_plan_with_pull(extra_modules=None) -> MigrationPlan:
    modules = {
        "oca_partner": ModulePlan(
            name="oca_partner",
            action="pull",
            origin=Origin(kind="oca", repo="OCA/partner-contact"),
        ),
    }
    if extra_modules:
        modules.update(extra_modules)
    return MigrationPlan(version=2, migration={}, modules=modules)


def _make_state_with_deps(target_depends_on) -> State:
    return State(
        version=2,
        source_ref="18.0",
        from_version="18.0",
        to_version="19.0",
        modules={
            "oca_partner": ModuleState(
                name="oca_partner",
                origin=Origin(kind="oca", repo="OCA/partner-contact"),
                target_depends_on=target_depends_on,
            )
        },
    )


class TestInsertGhostModules:
    def test_kb_builtin_skipped(self):
        plan = _make_plan_with_pull()
        state = _make_state_with_deps(["base", "mail"])
        from oops.core.models import Result

        outer = Result()
        result = _insert_ghost_modules(plan, state, {"base": {}, "mail": {}}, outer)
        assert result == {}
        assert "base" not in plan.modules
        assert "mail" not in plan.modules

    def test_unknown_dep_becomes_ghost(self):
        plan = _make_plan_with_pull()
        state = _make_state_with_deps(["new_dep"])
        from oops.core.models import Result

        outer = Result()
        result = _insert_ghost_modules(plan, state, {}, outer)
        assert "new_dep" in result
        assert result["new_dep"] == "oca_partner"
        ghost = plan.modules["new_dep"]
        assert ghost.action is None
        assert ghost.origin.kind == "new"
        assert ghost.review is True

    def test_already_in_plan_skipped(self):
        existing = ModulePlan(name="existing_dep", action="port", origin=Origin(kind="custom"))
        plan = _make_plan_with_pull({"existing_dep": existing})
        state = _make_state_with_deps(["existing_dep"])
        from oops.core.models import Result

        outer = Result()
        result = _insert_ghost_modules(plan, state, {}, outer)
        assert result == {}

    def test_no_target_depends_skipped(self):
        plan = _make_plan_with_pull()
        state = _make_state_with_deps(None)
        from oops.core.models import Result

        outer = Result()
        result = _insert_ghost_modules(plan, state, {}, outer)
        assert result == {}


# ---------------------------------------------------------------------------
# Unit tests — _enrich_ghost_modules
# ---------------------------------------------------------------------------


class TestEnrichGhostModules:
    def _make_plan_with_ghost(self, ghost_name="ghost_mod"):
        return MigrationPlan(
            version=2,
            migration={},
            modules={
                "oca_parent": ModulePlan(
                    name="oca_parent",
                    action="pull",
                    origin=Origin(kind="oca", repo="OCA/some-repo"),
                ),
                ghost_name: ModulePlan(
                    name=ghost_name,
                    action=None,
                    origin=Origin(kind="new"),
                    review=True,
                ),
            },
        )

    def test_resolved_becomes_pull(self):
        plan = self._make_plan_with_ghost()
        ghost_parents = {"ghost_mod": "oca_parent"}
        from oops.core.models import Result

        outer = Result()
        with patch(
            "oops.commands.migrate.plan.check_upstream_graphql",
            return_value={"ghost_mod": True},
        ):
            _enrich_ghost_modules(plan, ghost_parents, "19.0", "fake-token", outer)

        mp = plan.modules["ghost_mod"]
        assert mp.action == "pull"
        assert mp.origin.repo == "OCA/some-repo"
        assert mp.origin.ref == "19.0"
        assert mp.review is True
        assert not outer.warnings

    def test_unresolved_warns(self):
        plan = self._make_plan_with_ghost()
        ghost_parents = {"ghost_mod": "oca_parent"}
        from oops.core.models import Result

        outer = Result()
        with patch(
            "oops.commands.migrate.plan.check_upstream_graphql",
            return_value={"ghost_mod": False},
        ):
            _enrich_ghost_modules(plan, ghost_parents, "19.0", "fake-token", outer)

        mp = plan.modules["ghost_mod"]
        assert mp.action is None
        assert outer.warnings

    def test_no_token_no_network_warns(self):
        plan = self._make_plan_with_ghost()
        ghost_parents = {"ghost_mod": "oca_parent"}
        from oops.core.models import Result

        outer = Result()
        with patch("oops.commands.migrate.plan.check_upstream_graphql") as mock_gql:
            _enrich_ghost_modules(plan, ghost_parents, "19.0", None, outer)
            mock_gql.assert_not_called()

        assert plan.modules["ghost_mod"].action is None
        assert outer.warnings

    def test_graphql_exception_warns(self):
        plan = self._make_plan_with_ghost()
        ghost_parents = {"ghost_mod": "oca_parent"}
        from oops.core.models import Result

        outer = Result()
        with patch(
            "oops.commands.migrate.plan.check_upstream_graphql",
            side_effect=RuntimeError("network fail"),
        ):
            _enrich_ghost_modules(plan, ghost_parents, "19.0", "fake-token", outer)

        assert plan.modules["ghost_mod"].action is None
        assert outer.warnings


# ---------------------------------------------------------------------------
# Integration test — ghost enrichment end-to-end
# ---------------------------------------------------------------------------


def test_plan_ghost_enrichment_integration(tmp_path):
    """builtin skipped, resolved → pull, unresolvable → warning + no action."""
    modules = {
        "oca_partner": ModuleState(
            name="oca_partner",
            origin=Origin(kind="oca", repo="OCA/partner-contact"),
            depends_on=[],
            upstream_available=True,
            target_depends_on=["base", "sibling_mod", "unknown_mod"],
        ),
    }
    _write_state(tmp_path, modules=modules)

    with _mock_repo(tmp_path):
        with patch("oops.commands.migrate.plan.load_odoo_kb", return_value={"base": {}}):
            with patch(
                "oops.commands.migrate.plan.check_upstream_graphql",
                return_value={"sibling_mod": True, "unknown_mod": False},
            ):
                result = CliRunner().invoke(main, [], obj={"token": "fake-token"})

    assert result.exit_code == 0, result.output

    plan_path = tmp_path / ".oops" / "migrate" / "plan.yml"
    data = yaml.safe_load(plan_path.read_text())

    # base is an Odoo builtin — not in plan at all
    assert "base" not in data["modules"]
    # sibling_mod resolved to pull via parent repo
    assert data["modules"]["sibling_mod"]["action"] == "pull"
    assert data["modules"]["sibling_mod"]["origin"]["repo"] == "OCA/partner-contact"
    # unknown_mod unresolved → no action (warns)
    assert data["modules"]["unknown_mod"].get("action") is None
    # warning about unknown_mod is in output
    assert "unknown_mod" in result.output
