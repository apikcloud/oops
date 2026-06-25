# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: apply.py — oops/commands/migrate/apply.py

"""
Execute the migration plan: create branches and run mechanical tooling.

A workshop preparer, NOT an automatic migrator. For each module in
topological dependency order it:
  - creates the target branch from source_ref,
  - dispatches on action:
      port → runs the resolved tool chain (odoo-module-migrator, pre-commit…),
      pull → records as ready (upstream handles the migration),
      drop → records as dropped (no branch, no tooling),
  - for rename / merge_with: executes the mechanical part (branch + directory
    rename) then lays a template commit with a human checklist,
  - records the result in status.yml after each module (resumable on failure).

Idempotent: modules already recorded as done in status.yml are skipped unless
--force is passed. Use --only to target specific modules.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml
from oops.commands.base import command, render_and_exit
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

from .common import (
    PLAN_FILE,
    STATUS_FILE,
    MigrationPlan,
    ModulePlan,
    artifact_path,
    build_graph,
    load_plan,
    resolve_branch,
    resolve_tools,
)

UTC = timezone.utc

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}

# ---------------------------------------------------------------------------
# Status journal dataclasses (status.yml — machine-owned)
# ---------------------------------------------------------------------------

ModuleStatus = str  # "done" | "skipped" | "failed" | "pending"


@dataclass
class ModuleRecord:
    """Execution record for one module in status.yml."""

    name: str
    action: str
    branch: Optional[str]
    status: ModuleStatus
    tools_run: list[str] = field(default_factory=list)
    error: Optional[str] = None
    applied_at: Optional[str] = None  # ISO 8601


@dataclass
class ApplyStatus:
    """status.yml — idempotency journal for apply."""

    version: int
    plan_source_ref: str
    from_version: str
    to_version: str
    modules: dict[str, ModuleRecord] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def _load_status(path: Path) -> Optional[ApplyStatus]:
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    modules = {name: ModuleRecord(**mod) for name, mod in data.get("modules", {}).items()}
    return ApplyStatus(
        version=data["version"],
        plan_source_ref=data["plan_source_ref"],
        from_version=data["from_version"],
        to_version=data["to_version"],
        modules=modules,
        started_at=data.get("started_at", ""),
    )


def _save_status(path: Path, status: ApplyStatus) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(status)
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


def _topo_sort(graph: dict[str, list[str]]) -> list[str]:
    """Return module names in topological order (dependencies first).

    Uses Kahn's algorithm. Raises OopsError on cycles (should not happen
    in a well-formed Odoo dependency graph, but better to surface it than
    silently produce a wrong order).
    """
    from collections import deque

    in_degree = {n: 0 for n in graph}
    for deps in graph.values():
        for d in deps:
            if d in in_degree:
                in_degree[d] += 1

    # Reverse: we want dependencies FIRST, so nodes with no in-edges go first.
    # Re-map: in_degree here counts "how many modules this one depends on"
    # We need the reverse: sort so that modules with no dependencies come first.
    in_degree = {n: 0 for n in graph}
    for node, deps in graph.items():
        for d in set(deps):
            if d in in_degree:
                in_degree[node] += 1  # node depends on d → node's in-degree++

    # Nodes with no deps first.
    queue: deque[str] = deque(sorted(n for n, deg in in_degree.items() if deg == 0))
    order: list[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for other, deps in graph.items():
            if node in deps:
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)

    if len(order) != len(graph):
        cycle_nodes = set(graph) - set(order)
        raise OopsError(f"Dependency cycle detected among: {', '.join(sorted(cycle_nodes))}")
    return order


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_plan(plan: MigrationPlan, outer: "Result[None]") -> None:
    """Pre-flight checks before touching git. Adds errors to outer."""
    names = set(plan.modules.keys())

    for name, mp in plan.modules.items():
        # Invariant: exactly one action.
        if mp.action is None:
            outer.add_error(f"Module '{name}' has no action — run `oops migrate plan` first.")
        # merge_with target must exist in the plan.
        if mp.merge_with:
            target = mp.merge_with.get("into")
            if target and target not in names:
                outer.add_error(f"Module '{name}': merge_with target '{target}' not in plan.")
        # rename target must not collide with an existing module.
        if mp.rename and mp.rename in names and mp.rename != name:
            outer.add_error(f"Module '{name}': rename target '{mp.rename}' already exists in plan.")


# ---------------------------------------------------------------------------
# Per-module execution
# ---------------------------------------------------------------------------


def _run_tools(tools: list[str], cwd: Path) -> list[str]:
    """Run each tool command in the module directory. Returns list of run tools.

    Raises subprocess.CalledProcessError on first failure.
    """
    run = []
    for tool_cmd in tools:
        log.debug(f"Running: {tool_cmd} (cwd={cwd})")
        subprocess.run(
            tool_cmd,
            shell=True,
            check=True,
            cwd=cwd,
        )
        run.append(tool_cmd)
    return run


def _apply_port(
    mp: ModulePlan,
    repo,
    repo_path: Path,
    source_ref: str,
    branch: str,
    dry_run: bool,
) -> list[str]:
    """Create branch + run tool chain for a port module.

    Returns the list of tools actually run.
    """
    module_path = repo_path / mp.name

    if not dry_run:
        # Create branch from source_ref if it doesn't exist.
        existing = [b.name for b in repo.branches]
        if branch not in existing:
            log.debug(f"Creating branch {branch!r} from {source_ref!r}")
            repo.git.checkout("-b", branch, source_ref)
        else:
            log.debug(f"Branch {branch!r} already exists, checking out")
            repo.git.checkout(branch)

        tools = resolve_tools(mp, {})
        if tools and module_path.exists():
            return _run_tools(tools, cwd=module_path)
        elif tools:
            log.warning(f"{mp.name}: module directory not found at {module_path}, skipping tools.")
    else:
        tools = resolve_tools(mp, {})
        log.info(f"[dry-run] would create branch {branch!r} and run: {tools}")

    return resolve_tools(mp, {})


def _apply_pull(
    mp: ModulePlan,
    repo,
    source_ref: str,
    branch: str,
    dry_run: bool,
) -> None:
    """For pull modules: create branch, no tooling needed.

    The actual migration content comes from upstream; the branch is a
    placeholder that `status` can observe.
    """
    if not dry_run:
        existing = [b.name for b in repo.branches]
        if branch not in existing:
            log.debug(f"Creating tracking branch {branch!r} from {source_ref!r}")
            repo.git.checkout("-b", branch, source_ref)
        else:
            log.debug(f"Branch {branch!r} already exists")
            repo.git.checkout(branch)
        repo.git.checkout(repo.active_branch.name)  # return to previous branch
    else:
        log.info(f"[dry-run] would create tracking branch {branch!r}")


def _apply_rename(
    mp: ModulePlan,
    repo,
    repo_path: Path,
    branch: str,
    dry_run: bool,
) -> None:
    """Mechanical rename: move the module directory, then lay a template commit."""
    new_name = mp.rename
    old_path = repo_path / mp.name
    new_path = repo_path / new_name

    if not dry_run:
        if old_path.exists() and not new_path.exists():
            log.debug(f"Renaming {mp.name} → {new_name}")
            old_path.rename(new_path)
            repo.index.add([str(new_path)])
            repo.index.remove([str(old_path)], r=True, f=True)

        _commit_template(
            repo,
            subject=f"[mig] rename {mp.name} → {new_name} (checklist)",
            checklist=[
                f"Update all `_inherit` references from '{mp.name}' to '{new_name}'",
                "Update XML IDs in data files",
                "Update ir.model.access references",
                "Search for string occurrences of the old name",
                "Run tests",
            ],
        )
    else:
        log.info(f"[dry-run] would rename {mp.name!r} → {new_name!r}")


def _apply_merge_with(
    mp: ModulePlan,
    repo,
    repo_path: Path,
    branch: str,
    dry_run: bool,
) -> None:
    """Mechanical merge_with: create branch, lay a template commit."""
    target = mp.merge_with.get("into", "?")

    if not dry_run:
        _commit_template(
            repo,
            subject=f"[mig] merge {mp.name} into {target} (checklist)",
            checklist=[
                f"Move models from '{mp.name}' into '{target}'",
                f"Move views and data files into '{target}'",
                f"Update all cross-references to use '{target}'",
                f"Remove '{mp.name}' module directory",
                "Add migration script for moved records",
                "Run tests",
            ],
        )
    else:
        log.info(f"[dry-run] would lay merge_with template: {mp.name!r} → {target!r}")


def _commit_template(repo, subject: str, checklist: list[str]) -> None:
    """Create an empty commit with a structured checklist message."""
    body = "\n".join(f"  [ ] {item}" for item in checklist)
    message = f"{subject}\n\n{body}\n"
    repo.index.commit(message)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@command(name="apply", help=__doc__)
@click.option(
    "--only",
    default=None,
    help="Comma-separated module names to apply (default: all).",
)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Re-apply modules already marked done in status.yml.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would happen without touching git.",
)
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
def main(ctx, only, force, dry_run, output_format, output_path):
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()

    repo, repo_path = require_repository()

    plan_path = artifact_path(repo_path, PLAN_FILE)
    status_path = artifact_path(repo_path, STATUS_FILE)

    # 1. Load plan.
    if not plan_path.exists():
        raise OopsError(f"No plan found at {plan_path}. Run `oops migrate plan` first.")
    plan: MigrationPlan = load_plan(plan_path)
    log.info(f"Loaded plan: {len(plan.modules)} module(s)")

    # 2. Validate before touching git.
    outer: Result[None] = Result()
    _validate_plan(plan, outer)
    if not outer.ok:
        raise OopsError("Plan validation failed:\n" + "\n".join(f"  {e}" for e in outer.errors))

    # 3. Load or init status.yml.
    migration = plan.migration
    apply_status = _load_status(status_path) or ApplyStatus(
        version=plan.version,
        plan_source_ref=migration.get("source_ref", ""),
        from_version=migration.get("from", ""),
        to_version=migration.get("to", ""),
    )

    # 4. Compute execution order — topological sort on the filtered graph.
    #    The graph uses post-intent names (rename/merge_with applied) so we
    #    sort on what will exist, not what currently exists.
    graph = build_graph(plan.modules, {})
    try:
        ordered = _topo_sort(graph)
    except OopsError as exc:
        raise OopsError(str(exc)) from exc

    # 5. Filter the work set.
    only_set = {m.strip() for m in only.split(",")} if only else None

    work: list[str] = []
    for name in ordered:
        if only_set and name not in only_set:
            continue
        rec = apply_status.modules.get(name)
        if rec and rec.status == "done" and not force:
            log.debug(f"{name}: already done, skipping (use --force to re-run)")
            continue
        work.append(name)

    if not work:
        raise OopsError("Nothing to apply — all selected modules are already done.")

    # 6. Execute.
    source_ref = migration.get("source_ref", "HEAD")

    rows: list[list] = []
    for name in work:
        mp = plan.modules[name]
        branch = mp.resolved_branch or resolve_branch(mp, plan.migration, plan.groups)
        tools_run: list[str] = []
        error: Optional[str] = None
        status: ModuleStatus = "pending"

        with live_progress(f"Applying {name} ({mp.action})…"):
            try:
                if mp.action == "port":
                    tools_run = _apply_port(mp, repo, repo_path, source_ref, branch, dry_run)
                    if mp.rename:
                        _apply_rename(mp, repo, repo_path, branch, dry_run)
                    if mp.merge_with:
                        _apply_merge_with(mp, repo, repo_path, branch, dry_run)
                    status = "done"

                elif mp.action == "pull":
                    _apply_pull(mp, repo, source_ref, branch, dry_run)
                    status = "done"

                elif mp.action == "drop":
                    # Nothing to execute — record as done.
                    log.debug(f"{name}: drop — no branch, no tooling")
                    status = "done"

            except subprocess.CalledProcessError as exc:
                error = f"Tool failed: {exc.cmd} (exit {exc.returncode})"
                outer.add_error(f"{name}: {error}")
                status = "failed"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                outer.add_error(f"{name}: {error}")
                status = "failed"

        # Record immediately — journal is resumable on failure.
        apply_status.modules[name] = ModuleRecord(
            name=name,
            action=mp.action or "",
            branch=branch if mp.action != "drop" else None,
            status=status,
            tools_run=tools_run,
            error=error,
            applied_at=datetime.now(UTC).isoformat() if not dry_run else None,
        )
        if not dry_run:
            _save_status(status_path, apply_status)

        rows.append(
            [
                name,
                mp.action or "",
                branch if mp.action != "drop" else "—",
                status,
                ", ".join(tools_run) if tools_run else "—",
                error or "—",
            ]
        )

    # 7. Report.
    from collections import Counter

    counts = Counter(r[3] for r in rows)

    result: Result[dict] = Result()
    result.data = {
        "cmd": f"Migration apply {migration.get('from')} → {migration.get('to')}",
        "dry_run": dry_run,
        "rows": rows,
        "metrics": {
            "total": len(rows),
            "done": counts["done"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
        },
    }
    result.merge(outer)

    from .presenters.apply import ApplyPresenter

    output = ApplyPresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)
