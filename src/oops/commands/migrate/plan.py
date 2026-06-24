# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: plan.py — oops/commands/migrate/plan.py

"""
Seed or reconcile plan.yml from the current state.

First run: creates plan.yml from state.yml, guessing an action per module
(marked review: true where guessed) so the human can refine it.

Subsequent runs (reconcile): a three-way merge between the previous plan,
the new state, and the human's intent —
  - human edits are preserved (intent is human-owned),
  - origin is refreshed (machine-owned),
  - new modules get a guessed action + review: true,
  - disappeared modules are flagged, not silently dropped.

Like `terraform plan`: shows the diff, does not decide. Refuses if any
module fails the invariant "exactly one action".
"""

from __future__ import annotations

from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.core.compat import Optional
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.output.formatters import FormatterRegistry, JsonFormatter, OutputFormatter, SimpleSummaryConsoleFormatter
from oops.services.git import require_repository

from .common import (
    PLAN_FILE,
    STATE_FILE,
    ModulePlan,
    Origin,
    Plan,
    State,
    _guess_action,
    _needs_review,
    artifact_path,
    load_plan,
    load_state,
    save_plan,
)

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="plan", help=__doc__)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--output-path", "output_path", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.pass_context
def main(ctx, output_format, output_path):
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()

    repo, repo_path = require_repository()

    state_path = artifact_path(repo_path, STATE_FILE)
    plan_path = artifact_path(repo_path, PLAN_FILE)

    # 1. Require a state.
    if not state_path.exists():
        raise OopsError(f"No state found at {state_path}. Run `oops migrate analyze` first.")
    state: State = load_state(state_path)

    # 2. Load existing plan (None on first run).
    existing_plan: Optional[Plan] = None
    if plan_path.exists():
        existing_plan = load_plan(plan_path)

    outer: Result[None] = Result()

    with live_progress("Reconciling plan…"):
        if existing_plan is None:
            new_plan: Optional[Plan] = _seed_plan(state)
        else:
            new_plan = _reconcile_plan(existing_plan, state, outer)

    # 3. Enforce the invariant: exactly one action per module.
    if new_plan is not None:
        for name, mp in new_plan.modules.items():
            if mp.action is None:
                outer.add_error(f"Module '{name}' has no action. Set one of: pull, port, drop, keep.")

    # 4. Persist plan.yml only if no errors.
    if outer.ok and new_plan is not None:
        save_plan(plan_path, new_plan)

    # 5. Build result for output.
    modules = new_plan.modules if new_plan else {}
    metrics = {
        "total": len(modules),
        "pull": sum(1 for m in modules.values() if m.action == "pull"),
        "port": sum(1 for m in modules.values() if m.action == "port"),
        "drop": sum(1 for m in modules.values() if m.action == "drop"),
        "keep": sum(1 for m in modules.values() if m.action == "keep"),
        "review": sum(1 for m in modules.values() if m.review),
    }

    result: Result[dict] = Result()
    result.data = {
        "cmd": "Migration plan",
        "plan_path": str(plan_path),
        "modules": modules,
        "metrics": metrics,
        "is_first_run": existing_plan is None,
    }
    result.merge(outer)

    from .presenters.plan import PlanPresenter
    output = PlanPresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)


def _seed_plan(state: State) -> Plan:
    """First run: build Plan from State, guessing one action per module."""
    modules: dict[str, ModulePlan] = {}
    for name, ms in state.modules.items():
        action = _guess_action(ms)
        review = _needs_review(ms, action)
        modules[name] = ModulePlan(
            name=name,
            action=action,
            origin=Origin(kind=ms.origin.kind, repo=ms.origin.repo, ref=ms.origin.ref),
            depends_on=ms.depends_on,
            review=review,
        )
    return Plan(
        version=state.version,
        migration={
            "from": state.from_version,
            "to": state.to_version,
            "source_ref": state.source_ref,
            "target_branch": f"{state.to_version}-mig/{{module}}",
            "strategy": "port",
            "branch_template": f"{state.to_version}-mig/{{module}}",
        },
        modules=modules,
    )


def _reconcile_plan(prev: Plan, state: State, outer: "Result[None]") -> Plan:
    """Three-way merge: preserve human intent; refresh machine fields."""
    modules: dict[str, ModulePlan] = {}

    for name, ms in state.modules.items():
        origin = Origin(kind=ms.origin.kind, repo=ms.origin.repo, ref=ms.origin.ref)
        if name in prev.modules:
            p = prev.modules[name]
            action = p.action
            review = p.review
            if action is None:
                action = _guess_action(ms)
                review = True
            modules[name] = ModulePlan(
                name=name,
                action=action,
                origin=origin,
                depends_on=ms.depends_on,
                group=p.group,
                tools=p.tools,
                merge_with=p.merge_with,
                rename=p.rename,
                priority=p.priority,
                reason=p.reason,
                review=review,
            )
        else:
            action = _guess_action(ms)
            modules[name] = ModulePlan(
                name=name,
                action=action,
                origin=origin,
                depends_on=ms.depends_on,
                review=True,
            )

    # Disappeared modules: flag, do NOT drop.
    for name, p in prev.modules.items():
        if name not in state.modules:
            outer.add_warning(f"Module '{name}' is in plan.yml but missing from state. Was it removed?")
            modules[name] = ModulePlan(
                name=name,
                action=p.action,
                origin=p.origin,
                depends_on=p.depends_on,
                group=p.group,
                tools=p.tools,
                merge_with=p.merge_with,
                rename=p.rename,
                priority=p.priority,
                reason=p.reason or "(disappeared from state — verify)",
                review=True,
            )

    return Plan(
        version=prev.version,
        migration=prev.migration,
        defaults=prev.defaults,
        groups=prev.groups,
        modules=modules,
    )
