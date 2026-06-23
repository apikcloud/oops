# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: apply.py — oops/commands/migrate/apply.py

"""
Execute the plan: create branches and run mechanical tooling per module.

A workshop preparer, NOT an automatic migrator. It creates branches in
topological dependency order, applies mechanical tools (odoo-module-migrator,
pre-commit, pyupgrade), and lays template commits for judgment operations
(rename, merge_with) — it never performs the business migration itself.

Idempotent via status.yml. Supports --force and --only.

Currently implemented: plan loading + validation only. Execution is staged
behind TODOs.
"""

from __future__ import annotations

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.exceptions import OopsError
from oops.core.logger import log
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.output.formatters import FormatterRegistry, JsonFormatter, OutputFormatter, SimpleSummaryConsoleFormatter
from oops.services.git import require_repository

from .common import (
    PLAN_FILE,
    Plan,
    artifact_path,
    load_plan,
)

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="apply", help=__doc__)
@click.option("--only", default=None, help="Comma-separated module names to apply (default: all).")
@click.option("-f", "--force", is_flag=True, help="Re-run modules already marked done in status.yml.")
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--output-path", "output_path", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.pass_context
def main(ctx, only, force, dry_run, output_format, output_path):
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()

    repo, repo_path = require_repository()
    outer: Result[None] = Result()

    plan_path = artifact_path(repo_path, PLAN_FILE)

    # ---- IMPLEMENTED: load the plan (the single source of intent) ----
    if not plan_path.exists():
        raise OopsError(f"No plan found at {plan_path}. Run `oops migrate plan` first.")

    plan: Plan = load_plan(plan_path)
    log.info(f"Loaded plan: {len(plan.modules)} module(s)")

    # ---- TODO: everything below is staged ----

    # 1. Load (or init) status.yml for idempotency.
    #    TODO: load_status(STATUS_FILE) → which modules are already done.

    # 2. Validate the plan before touching git.
    #    TODO: re-check the "exactly one action" invariant; verify merge_with
    #          targets exist; verify rename targets don't collide; verify
    #          group branch consistency. Refuse on any inconsistency.

    # 3. Compute execution order.
    #    TODO: topological sort on the dependency graph. Note: the graph must
    #          reflect post-intent names (after rename/merge_with), not the
    #          raw manifest names, or ordering targets vanished modules.

    # 4. Filter the work set.
    #    TODO: apply --only; skip modules already done unless --force.

    # 5. Execute per module, recording status as we go (idempotent journal).
    #    TODO: for each module in order:
    #      - create branch from branch_template (or group branch)
    #      - dispatch on action:
    #          pull  → point at upstream/PR ref, no porting
    #          port  → run mechanical tools (migrator, pre-commit, pyupgrade)
    #          drop  → remove module, record reason
    #          keep  → no-op
    #      - for rename / merge_with: do the MECHANICAL part only, then lay a
    #        template commit with a human checklist (do not port the business)
    #      - update status.yml after each module (resumable on failure)

    # 6. Report the execution journal.
    result: Result[dict] = Result()
    result.data = {
        "cmd": "Migration apply",
        "rows": [],  # TODO: one row per module (action, branch, result)
        "metrics": {},  # TODO: counts (done, skipped, failed)
    }

    # TODO: ApplyPresenter + render_and_exit.
    raise NotImplementedError("apply: execution staged — plan loading only for now")
