# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: workflow.py — src/oops/output/workflow.py

"""
Shared scenario for mutating commands: select → present → confirm → apply.
The workflow owns the common interaction flow; the command provides how to
build the plan and how to apply a single action, and handles its own
side effects (commit) and final rendering afterwards.
"""

from __future__ import annotations

from typing import Callable

from oops.core.compat import Tuple
from oops.core.exceptions import AppAbort, EarlyExit
from oops.core.models import Plan, PlanAction, Result, Rows
from oops.output.helper import render_plan
from oops.utils.render import colorize, conclude, prompt_choices, prompt_confirm

# Columns for the post-execution status table.
DEFAULT_STATUS_COLUMNS: list[tuple[str, str, str]] = [
    ("Name", "brand.primary", "left"),
    ("Status", "dim", "center"),
]

# Signature of the per-action executor supplied by each command.
# Returns (status_label, ok).
ApplyFn = Callable[["PlanAction"], Tuple[str, bool]]


def run_mutation_workflow(
    *,
    plan: Plan,
    apply: ApplyFn,
    outer: Result,
    title: str,
    force: bool = False,
    select: bool = True,
    select_prompt: str = "Select item(s): ",
    empty_message: str = "Nothing to do.",
) -> Result[Rows]:
    """Run the shared mutation scenario and return the execution result.

    Steps:
        1. Bail out early if the plan has nothing actionable.
        2. Optionally let the user select a subset (skipped when --force).
        3. Present the plan.
        4. Ask for confirmation (skipped when --force).
        5. Execute each action via `apply`, collecting status + metrics.

    The workflow does NOT commit and does NOT render the result — the calling
    command does that, so it can run its own side effects between execution
    and rendering.

    Args:
        plan: The plan to execute (already built, optionally restricted).
        apply: Callback executing one action, returning (status_label, ok).
        outer: Collects per-action errors raised during execution.
        title: Title for the result table.
        force: Skip selection and confirmation prompts.
        select: Whether to offer interactive selection at all.
        select_prompt: Prompt text for the selection step.
        empty_message: Message shown when there is nothing to do.

    Returns:
        A Result[Rows] describing what was executed.

    Raises:
        EarlyExit: Nothing to do (before or after selection).
        AppAbort: User cancelled selection or confirmation.
    """
    # 1. Nothing to do?
    if not plan.actionable:
        conclude(True, empty_message)
        raise EarlyExit()

    # 2. Interactive selection (unless --force)
    if select and not force:
        available = {a.label for a in plan.actionable}
        selected = prompt_choices(select_prompt, available, available)
        if not selected:
            raise AppAbort()
        plan.apply_selection(selected)

        if not plan.actionable:
            conclude(True, empty_message)
            raise EarlyExit()

    # 3. Present the plan
    render_plan(plan)

    # 4. Confirmation (unless --force)
    if not force and not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    # 5. Execute
    result: Result[Rows] = Result(
        Rows(
            title=title,
            columns=DEFAULT_STATUS_COLUMNS,
            rows=[],
            metrics={"total": len(plan.actionable), "success": 0, "failed": 0},
        )
    )
    assert result.data is not None

    for action in plan.actionable:
        try:
            status, ok = apply(action)
            result.data.rows.append([action.label, status])
            result.data.metrics["success" if ok else "failed"] += 1
        except Exception as err:  # noqa: BLE001 — surfaced via outer, not swallowed
            outer.add_error(f"{action.label}: {err}")
            result.data.rows.append([action.label, colorize("failed", "red")])
            result.data.metrics["failed"] += 1

    return result
