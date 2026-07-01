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

After seed/reconcile, the plan is enriched with computed machine fields:
  - dependency graph (effective: source for port, target for pull),
  - descendant counts and calculated priorities,
  - ghost modules (deps required by pull targets but missing from the plan),
  - resolved_branch and resolved_tools per module.

Like `terraform plan`: shows the diff, does not decide. Refuses if any
module fails the invariant "exactly one action".
"""

from __future__ import annotations

from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.utils.render import warn_experimental
from oops.core.compat import Optional
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.services.git import require_repository
from oops.services.github import check_upstream_graphql
from oops.services.kb import load_odoo_kb

from .common import (
    PLAN_FILE,
    STATE_FILE,
    MigrationPlan,
    ModulePlan,
    Origin,
    State,
    _guess_action,
    _needs_review,
    artifact_path,
    build_graph,
    calculate_priority,
    compute_descendant_counts,
    get_dest_branch,
    load_plan,
    load_state,
    resolve_branch,
    resolve_tools,
    save_plan,
)

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="plan", help=__doc__)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
)
@click.pass_context
def main(ctx, output_format, output_path):
    """Seed or reconcile plan.yml from the current state."""
    warn_experimental()
    token: Optional[str] = (ctx.obj or {}).get("token") or None
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()

    repo, repo_path = require_repository()

    state_path = artifact_path(repo_path, STATE_FILE)
    plan_path = artifact_path(repo_path, PLAN_FILE)

    # 1. Require a state — analyze is the mandatory entry point.
    if not state_path.exists():
        raise OopsError(f"No state found at {state_path}. Run `oops migrate analyze` first.")
    state: State = load_state(state_path)

    # 2. Load existing plan (None on first run).
    existing_plan: Optional[MigrationPlan] = None
    if plan_path.exists():
        existing_plan = load_plan(plan_path)

    outer: Result[None] = Result()

    with live_progress("Reconciling plan…"):
        # 3. Seed or reconcile — human intent is preserved.
        if existing_plan is None:
            new_plan = _seed_plan(state)
        else:
            new_plan = _reconcile_plan(existing_plan, state, outer)

        # 4. Detect ghost modules: deps required by pull targets that are
        #    not in the plan and not Odoo builtins (per the global KB).
        #    Enrich resolved ghosts via their parent repo (requires token).
        kb_modules = load_odoo_kb(state.to_version)
        ghost_parents = _insert_ghost_modules(new_plan, state, kb_modules, outer)
        _enrich_ghost_modules(new_plan, ghost_parents, state.to_version, token, outer)

        # 5. Compute the dependency graph and enrich all machine fields.
        _enrich_machine_fields(new_plan, state)

    # 6. Enforce the invariant: exactly one action per module, or refuse.
    for name, mp in new_plan.modules.items():
        if mp.action is None:
            outer.add_warning(f"Module '{name}' has no action — set one of: pull, port, drop.")

    # 7. Persist plan.yml only when there are no errors.
    if outer.ok:
        save_plan(plan_path, new_plan)

    # 8. Build result for output.
    modules = new_plan.modules
    metrics = {
        "total": len(modules),
        "pull": sum(1 for m in modules.values() if m.action == "pull"),
        "port": sum(1 for m in modules.values() if m.action == "port"),
        "drop": sum(1 for m in modules.values() if m.action == "drop"),
        "new": sum(1 for m in modules.values() if m.origin and m.origin.kind == "new"),
        "review": sum(1 for m in modules.values() if m.review),
        "critical": sum(1 for m in modules.values() if m.calculated_priority == "critical"),
        "high": sum(1 for m in modules.values() if m.calculated_priority == "high"),
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


# ---------------------------------------------------------------------------
# Seed — first run
# ---------------------------------------------------------------------------


def _seed_plan(state: State) -> MigrationPlan:
    """Build a MigrationPlan from State on first run.

    Guesses one action per module; marks uncertain ones review=True.
    Machine fields (priorities, resolved_*) are filled by _enrich_machine_fields
    after this call.
    """
    modules: dict[str, ModulePlan] = {}
    for name, ms in state.modules.items():
        action = _guess_action(ms)
        review = _needs_review(ms, action)
        pr_url = ms.upstream_prs[0]["url"] if ms.upstream_prs else None
        modules[name] = ModulePlan(
            name=name,
            action=action,
            origin=Origin(kind=ms.origin.kind, repo=ms.origin.repo, ref=ms.origin.ref, pr=pr_url),
            depends_on=ms.depends_on,
            review=review,
        )
    return MigrationPlan(
        version=state.version,
        migration={
            "from": state.from_version,
            "to": state.to_version,
            "source_ref": state.source_ref,
            "dest_branch": "main",
            "branch_template": f"mig/{state.to_version}/{{module}}",
        },
        modules=modules,
    )


# ---------------------------------------------------------------------------
# Reconcile — subsequent runs (three-way merge)
# ---------------------------------------------------------------------------


def _reconcile_plan(prev: MigrationPlan, state: State, outer: "Result[None]") -> MigrationPlan:
    """Three-way merge: preserve human intent, refresh machine fields.

    - Human fields are taken from prev (the human's edits).
    - origin and depends_on are refreshed from state (machine).
    - New modules in state get a guessed action + review=True.
    - Disappeared state modules are flagged with a warning, NOT dropped;
      `new` modules (origin.kind=="new") are silently preserved — they are
      intentionally absent from state.
    - Machine computed fields (priorities, resolved_*) are left at their
      defaults here; _enrich_machine_fields fills them afterwards.
    """
    modules: dict[str, ModulePlan] = {}

    # Modules present in the new state.
    for name, ms in state.modules.items():
        pr_url = ms.upstream_prs[0]["url"] if ms.upstream_prs else None
        origin = Origin(kind=ms.origin.kind, repo=ms.origin.repo, ref=ms.origin.ref, pr=pr_url)
        if name in prev.modules:
            p = prev.modules[name]
            action = p.action
            review = p.review
            # If action was cleared by a previous failed plan, re-guess.
            if action is None:
                action = _guess_action(ms)
                review = True
            modules[name] = ModulePlan(
                name=name,
                action=action,
                # Machine — refreshed from state.
                origin=origin,
                depends_on=ms.depends_on,
                # Human — preserved from prev.
                level=p.level,
                strategy=p.strategy,
                group=p.group,
                tools=p.tools,  # None vs [] preserved via load_plan
                merge_with=p.merge_with,
                rename=p.rename,
                priority=p.priority,
                reason=p.reason,
                review=review,
                pr=p.pr,
                repo=p.repo,
            )
        else:
            # New module in state, not yet in the plan.
            action = _guess_action(ms)
            modules[name] = ModulePlan(
                name=name,
                action=action,
                origin=origin,
                depends_on=ms.depends_on,
                review=True,
            )

    # Modules in prev but absent from the new state.
    for name, p in prev.modules.items():
        if name in modules:
            continue
        if p.origin and p.origin.kind == "new":
            # Intentionally absent from state — preserve silently.
            modules[name] = p
        else:
            # Disappeared from state — flag, do not drop.
            outer.add_warning(
                f"Module '{name}' is in plan.yml but missing from state. Was it removed from the repository?"
            )
            modules[name] = ModulePlan(
                name=name,
                action=p.action,
                origin=p.origin,
                depends_on=p.depends_on,
                level=p.level,
                strategy=p.strategy,
                group=p.group,
                tools=p.tools,
                merge_with=p.merge_with,
                rename=p.rename,
                priority=p.priority,
                reason=p.reason or "(disappeared from state — verify)",
                review=True,
                pr=p.pr,
                repo=p.repo,
            )

    migration = dict(prev.migration)
    migration.setdefault("dest_branch", get_dest_branch(prev.migration))
    migration.pop("target_branch", None)  # legacy template key, superseded by dest_branch
    migration.pop("strategy", None)  # dead key — never read, removed from seed

    return MigrationPlan(
        version=prev.version,
        migration=migration,
        defaults=prev.defaults,
        groups=prev.groups,
        modules=modules,
    )


# ---------------------------------------------------------------------------
# Ghost module detection
# ---------------------------------------------------------------------------


def _insert_ghost_modules(
    plan: MigrationPlan,
    state: State,
    kb_modules: dict,
    outer: "Result[None]",
) -> "dict[str, str]":
    """Detect deps required by pull targets but missing from the plan.

    A dep present in the global KB is an Odoo builtin (the global KB holds only
    community + enterprise modules) — it is provided by the target install and
    needs no migration action, so it is skipped entirely.

    Remaining ghosts are inserted with action=None + review=True. Returns a
    mapping ghost_name -> parent_name for the enrichment step.
    """
    plan_names = set(plan.modules.keys())
    ghost_parents: dict[str, str] = {}

    for name, mp in list(plan.modules.items()):
        if mp.action != "pull":
            continue
        ms = state.modules.get(name)
        if ms is None or ms.target_depends_on is None:
            continue
        for dep in ms.target_depends_on:
            if dep in plan_names or dep in kb_modules:
                continue
            plan.modules[dep] = ModulePlan(
                name=dep,
                action=None,
                origin=Origin(kind="new"),
                review=True,
                reason=f"required by '{name}' in target manifest",
            )
            plan_names.add(dep)
            ghost_parents[dep] = name

    return ghost_parents


def _enrich_ghost_modules(
    plan: MigrationPlan,
    ghost_parents: "dict[str, str]",
    to_version: str,
    token: "Optional[str]",
    outer: "Result[None]",
) -> None:
    """Resolve ghosts (non-builtin new deps) against their parent's repo.

    A ghost found in its parent's repo at the target version ships with that
    repo: set action=pull and fill origin. Unresolved ghosts get a warning and
    keep action=None so the invariant forces a human decision.

    Source 2 is network-backed and only runs with a token; without one, every
    ghost is treated as unresolved.
    """
    if not ghost_parents:
        return

    ghosts_by_repo: dict[str, list[str]] = {}
    parent_of: dict[str, ModulePlan] = {}
    for ghost, parent_name in ghost_parents.items():
        parent = plan.modules.get(parent_name)
        repo = (parent.repo if parent else None) or (parent.origin.repo if (parent and parent.origin) else None)
        if not (parent and repo and token):
            continue
        ghosts_by_repo.setdefault(repo, []).append(ghost)
        parent_of[ghost] = parent

    available: dict[str, bool] = {}
    if ghosts_by_repo:
        try:
            assert token is not None
            available = check_upstream_graphql(ghosts_by_repo, to_version, token)
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Ghost repo lookup failed ({exc}); ghosts left unresolved.")
            available = {}

    for ghost, parent_name in ghost_parents.items():
        if available.get(ghost):
            parent = parent_of[ghost]
            mp = plan.modules[ghost]
            mp.action = "pull"
            if parent.origin:
                mp.origin = Origin(
                    kind=parent.origin.kind,
                    repo=parent.origin.repo,
                    ref=to_version,
                )
                mp.reason = f"required by '{parent_name}'; found in {parent.origin.repo}"
            mp.review = True
        else:
            p = plan.modules.get(parent_name)
            repo = (p.repo if p else None) or (p.origin.repo if (p and p.origin) else None)
            outer.add_warning(
                f"Module '{ghost}' (required by '{parent_name}') not found in the "
                f"global KB or in {repo or 'its parent repo'} — assign an action "
                "(pull / port / drop)."
            )


# ---------------------------------------------------------------------------
# Machine field enrichment (priorities, resolved_branch, resolved_tools)
# ---------------------------------------------------------------------------


def _enrich_machine_fields(plan: MigrationPlan, state: State) -> None:
    """Compute and write all machine fields onto ModulePlan objects.

    Called after seed/reconcile and ghost insertion, so the full module set
    is known. Mutates the plan in place — these fields are never hand-edited.

    Steps:
        1. Build the effective dependency graph (source for port, target for pull).
        2. Compute descendant counts via reverse BFS.
        3. Derive calculated_priority from counts.
        4. Resolve branch name (respecting group exceptions).
        5. Resolve tool list (respecting tools=[] vs tools=None).
    """
    graph = build_graph(plan.modules, state.modules)
    counts = compute_descendant_counts(graph)

    for name, mp in plan.modules.items():
        # 3. Priority.
        mp.descendant_count = counts.get(name, 0)
        mp.calculated_priority = calculate_priority(mp.descendant_count)

        # 4. Resolved branch — skip for drop (no branch needed).
        if mp.action != "drop":
            mp.resolved_branch = resolve_branch(mp, plan.migration, plan.groups)
        else:
            mp.resolved_branch = None

        # 5. Resolved tools — skip for pull and drop (no porting work).
        if mp.action == "port":
            mp.resolved_tools = resolve_tools(mp, plan.defaults)
        else:
            mp.resolved_tools = None
