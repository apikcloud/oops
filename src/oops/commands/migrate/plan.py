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
from oops.commands.base import command
from oops.core.compat import Optional
from oops.core.logger import live_progress
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.output.formatters import FormatterRegistry, JsonFormatter, OutputFormatter, SimpleSummaryConsoleFormatter
from oops.services.git import require_repository

from .common import (
    PLAN_FILE,
    STATE_FILE,
    Plan,
    State,
    artifact_path,
    load_plan,
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
    outer: Result[None] = Result()

    state_path = artifact_path(repo_path, STATE_FILE)
    plan_path = artifact_path(repo_path, PLAN_FILE)

    # 1. Require a state. analyze is the mandatory entry point.
    #    TODO: load_state(state_path); error clearly if missing
    #          ("run `oops migrate analyze` first").
    state: Optional[State] = None  # TODO

    # 2. Load the existing plan if any (None on first run).
    existing_plan: Optional[Plan] = None
    if plan_path.exists():
        existing_plan = load_plan(plan_path)

    with live_progress("Reconciling plan…"):
        if existing_plan is None:
            # 3a. First run: seed plan from state, guessing actions.
            #     TODO: for each module, guess action (pull/port/drop/keep),
            #           mark review: true, attach origin from state.
            new_plan: Optional[Plan] = None  # TODO
        else:
            # 3b. Reconcile: three-way merge (prev plan, new state, intent).
            #     TODO:
            #       - preserve human intent fields (action, tools, merge_with…)
            #       - refresh origin from state (machine-owned)
            #       - new module → guessed action + review: true
            #       - disappeared module → flag (do not drop)
            #       - CRITICAL: distinguish "absent" vs "explicitly emptied"
            #         so re-seed never repopulates a field the human cleared.
            new_plan = None  # TODO

    # 4. Enforce the invariant before writing: exactly one action per module.
    #    TODO: collect modules with action is None → outer.add_error per hole.
    #          If any error, do NOT write the plan (refuse, like terraform).

    # 5. Persist plan.yml (preserving comments/order — ruamel round-trip).
    if outer.ok and new_plan is not None:
        save_plan(plan_path, new_plan)

    # 6. Report the diff (added / changed-origin / needs-review / disappeared).
    result: Result[dict] = Result()
    result.data = {
        "cmd": "Migration plan",
        "rows": [],  # TODO: one row per module with its diff status
        "metrics": {},  # TODO: counts (new, review, dropped, unchanged)
    }
    # TODO: PlanPresenter (human diff table + json), then:
    # render_and_exit(result, formatter, output, output_format, output_path)
    raise NotImplementedError("plan: reconcile + presenter + render")
