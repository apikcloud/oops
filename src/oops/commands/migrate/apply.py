# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: apply.py — oops/commands/migrate/apply.py

"""
Execute the migration plan: create branches and run mechanical tooling.

A workshop preparer, NOT an automatic migrator. Operates exclusively in
the git worktree created by `oops migrate prepare` — the source branch in
the main repository is never touched.

For each module in topological order:
  port → create branch from dest base, extract module via git archive,
         commit initial state, run tool chain, commit result.
  pull → aggregated on a single branch (pull_branch from plan.migration):
         oops submodule add OR oops pr add, depending on origin.pr.
  drop → no branch, no tooling, recorded as done.

Idempotent via status.yml. --force re-runs done modules. --only targets
specific modules. --pull-only / --port-only filters by action.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml
from oops.commands.base import command, render_and_exit
from oops.core.compat import Optional
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.io.file import desired_path
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.services.git import require_repository
from oops.services.github import get_pull_request
from oops.utils.net import parse_pull_request_url

from .common import (
    PLAN_FILE,
    STATUS_FILE,
    MigrationPlan,
    ModulePlan,
    artifact_path,
    build_graph,
    get_dest_branch,
    get_pull_branch,
    get_worktree_path,
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
# Status journal (status.yml — machine-owned)
# ---------------------------------------------------------------------------

ModuleStatus = str  # "done" | "skipped" | "failed" | "pending"


@dataclass
class ModuleRecord:
    """Execution record for one module."""

    name: str
    action: str
    branch: Optional[str]
    status: ModuleStatus
    tools_run: list[str] = field(default_factory=list)
    error: Optional[str] = None
    applied_at: Optional[str] = None


@dataclass
class ApplyStatus:
    """status.yml — idempotency journal."""

    version: int
    plan_source_ref: str
    from_version: str
    to_version: str
    modules: dict[str, ModuleRecord] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Set by prepare:
    prepared: bool = False
    worktree_path: Optional[str] = None
    dest_branch: Optional[str] = None


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
        prepared=data.get("prepared", False),
        worktree_path=data.get("worktree_path"),
        dest_branch=data.get("dest_branch"),
    )


def _save_status(path: Path, status: ApplyStatus) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(status)
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------


def _topo_sort(graph: dict[str, list[str]]) -> list[str]:
    from collections import deque

    in_degree = {n: 0 for n in graph}
    for node, deps in graph.items():
        for d in set(deps):
            if d in in_degree:
                in_degree[node] += 1

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
        raise OopsError(f"Dependency cycle detected: {', '.join(sorted(cycle_nodes))}")
    return order


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------


def _validate_plan(plan: MigrationPlan, outer: "Result[None]") -> None:
    names = set(plan.modules.keys())
    for name, mp in plan.modules.items():
        if mp.action is None:
            outer.add_error(f"'{name}' has no action — run `oops migrate plan` first.")
        if mp.merge_with:
            target = mp.merge_with.get("into")
            if target and target not in names:
                outer.add_error(f"'{name}': merge_with target '{target}' not in plan.")
        if mp.rename and mp.rename in names and mp.rename != name:
            outer.add_error(f"'{name}': rename target '{mp.rename}' already exists.")


# ---------------------------------------------------------------------------
# Worktree git helpers
# ---------------------------------------------------------------------------


def _wt_run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the worktree directory."""
    log.debug(f"$ {' '.join(cmd)}  (cwd={cwd})")
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def _wt_branch_exists(wt_path: Path, branch: str) -> bool:
    r = _wt_run(["git", "branch", "--list", branch], wt_path, check=False)
    return bool(r.stdout.strip())


def _wt_current_branch(wt_path: Path) -> str:
    return _wt_run(["git", "branch", "--show-current"], wt_path).stdout.strip()


def _wt_checkout(wt_path: Path, branch: str, create_from: Optional[str] = None) -> None:
    """Checkout branch in worktree, optionally creating it from create_from."""
    if create_from:
        _wt_run(["git", "checkout", "-b", branch, create_from], wt_path)
    else:
        _wt_run(["git", "checkout", branch], wt_path)


def _extract_module(
    repo,
    source_ref: str,
    module_name: str,
    wt_path: Path,
) -> None:
    """Extract module directory from source_ref into the worktree via git archive.

    Uses: git archive <source_ref> <module>/ | tar -x -C <wt_path>
    This copies the file tree at source_ref without touching the working
    directory of the main repository.
    """
    archive = subprocess.run(
        ["git", "archive", source_ref, f"{module_name}/"],
        cwd=repo.working_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["tar", "-x", "-C", str(wt_path)],
        input=archive.stdout,
        check=True,
        capture_output=True,
    )


def _wt_commit(wt_path: Path, message: str, add_path: Optional[str] = None) -> None:
    if add_path:
        _wt_run(["git", "add", add_path], wt_path)
    else:
        _wt_run(["git", "add", "-A"], wt_path)
    _wt_run(["git", "commit", "-m", message], wt_path)


def _wt_commit_template(wt_path: Path, subject: str, checklist: list[str]) -> None:
    body = "\n".join(f"  [ ] {item}" for item in checklist)
    message = f"{subject}\n\n{body}\n"
    _wt_run(["git", "commit", "--allow-empty", "-m", message], wt_path)


def _run_tools(tools: list[str], cwd: Path) -> list[str]:
    """Run tool commands in module directory. Returns list of tools run."""
    run = []
    for tool_cmd in tools:
        log.debug(f"Tool: {tool_cmd}")
        subprocess.run(tool_cmd, shell=True, check=True, cwd=cwd)
        run.append(tool_cmd)
    return run


# ---------------------------------------------------------------------------
# Per-action executors
# ---------------------------------------------------------------------------


def _apply_port(
    mp: ModulePlan,
    repo,
    wt_path: Path,
    dest_branch: str,
    source_ref: str,
    branch: str,
    plan_defaults: dict,
    dry_run: bool,
) -> list[str]:
    """Port workflow:
    1. Create branch from dest base.
    2. Extract module via git archive.
    3. Commit initial state.
    4. Run tool chain.
    5. Commit tooling result.
    6. Handle rename / merge_with.
    """
    module_path = wt_path / mp.name
    tools = resolve_tools(mp, plan_defaults)

    if dry_run:
        log.info(f"[dry-run] {mp.name}: branch={branch!r}, extract from {source_ref!r}, tools={tools}")
        return tools

    # 1. Create branch from destination base.
    if _wt_branch_exists(wt_path, branch):
        _wt_checkout(wt_path, branch)
        log.debug(f"{mp.name}: branch {branch!r} already exists, checking out")
    else:
        _wt_checkout(wt_path, branch, create_from=dest_branch)

    # 2. Extract module from source ref.
    _extract_module(repo, source_ref, mp.name, wt_path)

    # 3. Commit initial state.
    _wt_commit(
        wt_path,
        f"[mig] {mp.name}: initial state from {source_ref}",
        add_path=mp.name,
    )

    # 4. Run tool chain.
    tools_run: list[str] = []
    if tools and module_path.exists():
        tools_run = _run_tools(tools, cwd=module_path)
        # 5. Commit tooling result.
        _wt_run(["git", "add", "-A"], wt_path)
        r = _wt_run(["git", "diff", "--cached", "--quiet"], wt_path, check=False)
        if r.returncode != 0:  # staged changes exist
            _wt_commit(
                wt_path,
                f"[mig] {mp.name}: mechanical tooling",
            )
    elif tools:
        log.warning(f"{mp.name}: module dir not found at {module_path}, skipping tools")

    # 6. rename / merge_with template commits.
    if mp.rename:
        _apply_rename(mp, wt_path, dry_run=False)
    if mp.merge_with:
        _apply_merge_with(mp, wt_path, dry_run=False)

    # Return to dest base for the next module.
    _wt_checkout(wt_path, dest_branch)

    return tools_run


def _apply_pull_batch(
    pull_modules: "list[tuple[ModulePlan, str]]",
    repo,
    wt_path: Path,
    dest_branch: str,
    pull_branch: str,
    to_version: str,
    dry_run: bool,
    token: str = "",
) -> "list[tuple[str, str, list[str], Optional[str]]]":
    """Aggregated pull workflow — all pull modules on one branch.

    Returns list of (name, status, tools_run, error).
    Delegates to oops submodule add / oops pr add via their service functions.
    """
    if dry_run:
        for mp, _ in pull_modules:
            pr = mp.pr or (mp.origin.pr if mp.origin else None)
            cmd = "oops pr add" if pr else "oops submodule add"
            log.info(f"[dry-run] {mp.name}: {cmd} on {pull_branch!r}")
        return [(mp.name, "done", [], None) for mp, _ in pull_modules]

    from git import Repo
    from oops.commands.submodules.add import add_submodule_flow

    # Create or checkout the pull branch.
    if _wt_branch_exists(wt_path, pull_branch):
        if _wt_current_branch(wt_path) != pull_branch:
            # Clean stray untracked dirs (e.g. leftover submodule dirs from a prior interrupted run).
            _wt_run(["git", "clean", "-fd"], wt_path, check=False)
            _wt_checkout(wt_path, pull_branch)
    else:
        _wt_checkout(wt_path, pull_branch, create_from=dest_branch)

    wt_repo = Repo(wt_path)
    results = []

    # Remove stale .gitmodules.lock left by an interrupted previous run.
    # Git refuses all submodule operations while this lock exists, causing
    # every module in the batch to fail with "Lock already existed".
    gitmodules_lock = wt_path / ".gitmodules.lock"
    if gitmodules_lock.exists():
        log.warning("Removing stale .gitmodules.lock from interrupted previous run.")
        gitmodules_lock.unlink()

    modules = [mp for mp, _ in pull_modules]
    prs = [mp for mp in modules if mp.pr or (mp.origin and mp.origin.pr)]
    subs = [mp for mp in modules if not mp.pr and (not mp.origin or not mp.origin.pr)]

    # Group by (repo_slug, ref) so each upstream repo is added once with
    # all its addons in a single call.
    repo_groups: dict[tuple[str, str], list[str]] = {}
    for mp in subs:
        repo_slug = mp.repo or (mp.origin.repo if mp.origin else "") or ""
        ref = (mp.origin.ref if mp.origin else None) or to_version
        if not repo_slug:
            continue
        repo_groups.setdefault((repo_slug, ref), []).append(mp.name)

    for (repo_slug, ref), addons in repo_groups.items():
        url = f"https://github.com/{repo_slug}.git"
        sub_path = wt_path / desired_path(url, prefix=str(config.submodules.current_path))

        # Per-addon presence check: symlink at worktree root OR dir inside submodule.
        present = [n for n in addons if (wt_path / n).exists() or (sub_path / n).exists()]
        missing = [n for n in addons if n not in present]

        results += [(n, "done", [], None) for n in present]
        if not missing:
            continue

        try:
            add_submodule_flow(
                repo=wt_repo,
                repo_path=wt_path,
                url=url,
                branch=ref,
                addons=",".join(missing),
                no_commit=False,
                force=True,
                pull_request=False,
                token="",
            )
            results += [(n, "done", [], None) for n in missing]
        except Exception as exc:  # noqa: BLE001
            # Clean up any lock left by the failed operation so later repos can proceed.
            if gitmodules_lock.exists():
                gitmodules_lock.unlink()
            results += [(n, "failed", [], str(exc)) for n in missing]

    for mp in prs:
        pr_sub_path = None
        effective_repo = mp.repo or (mp.origin.repo if mp.origin else None)
        if effective_repo:
            pr_sub_path = wt_path / desired_path(
                f"https://github.com/{effective_repo}.git",
                prefix=str(config.submodules.current_path),
                pull_request=True,
            )
        if (wt_path / mp.name).exists() or (pr_sub_path is not None and (pr_sub_path / mp.name).exists()):
            log.debug(f"{mp.name}: addon already present, marking done")
            results.append((mp.name, "done", [], None))
            continue
        pr_url = mp.pr or (mp.origin.pr if mp.origin else None)
        if not pr_url:
            results.append((mp.name, "failed", [], "no PR URL in origin"))
            continue
        try:
            pr_owner, pr_repo_name, pr_number = parse_pull_request_url(pr_url)
            pr = get_pull_request(pr_owner, pr_repo_name, pr_number, token)
            if not pr.head_repo_url or not pr.head_ref:
                raise OopsError(f"PR #{pr_number} head repository is unavailable (fork deleted?)")
            add_submodule_flow(
                repo=wt_repo,
                repo_path=wt_path,
                url=pr.head_repo_url,
                branch=pr.head_ref,
                addons=mp.name,
                no_commit=False,
                force=True,
                pull_request=True,
                token=token,
                commit_message_name="pr_add",
                extra_commit_kwargs={"pr_url": pr_url},
            )
            results.append((mp.name, "done", [], None))
        except Exception as exc:  # noqa: BLE001
            if gitmodules_lock.exists():
                gitmodules_lock.unlink()
            results.append((mp.name, "failed", [], str(exc)))

    # Return to dest base — best-effort; failure must not corrupt module statuses.
    try:
        if _wt_current_branch(wt_path) != dest_branch:
            _wt_checkout(wt_path, dest_branch)
    except subprocess.CalledProcessError as exc:
        log.warning(f"Could not return worktree to {dest_branch!r}: {exc.stderr.strip()}")

    return results


def _apply_rename(mp: ModulePlan, wt_path: Path, dry_run: bool) -> None:
    new_name = mp.rename
    if not new_name:
        return
    old_path = wt_path / mp.name
    new_path = wt_path / new_name

    if dry_run:
        log.info(f"[dry-run] rename {mp.name!r} → {new_name!r}")
        return

    if old_path.exists() and not new_path.exists():
        old_path.rename(new_path)
        _wt_run(["git", "add", "-A"], wt_path)

    _wt_commit_template(
        wt_path,
        subject=f"[mig] rename {mp.name} → {new_name} (checklist)",
        checklist=[
            f"Update all `_inherit` references from '{mp.name}' to '{new_name}'",
            "Update XML IDs in data files",
            "Update ir.model.access references",
            "Search for string occurrences of the old name",
            "Run tests",
        ],
    )


def _apply_merge_with(mp: ModulePlan, wt_path: Path, dry_run: bool) -> None:
    if not mp.merge_with:
        return
    target = mp.merge_with.get("into", "?")

    if dry_run:
        log.info(f"[dry-run] merge_with {mp.name!r} → {target!r}")
        return

    _wt_commit_template(
        wt_path,
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


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@command(name="apply", help=__doc__)
@click.option("--only", default=None, help="Comma-separated module names.")
@click.option("-f", "--force", is_flag=True, help="Re-apply already-done modules.")
@click.option("--pull-only", is_flag=True, help="Process pull modules only.")
@click.option("--port-only", is_flag=True, help="Process port modules only.")
@click.option("--dry-run", is_flag=True, help="Show what would happen, no git changes.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--output-path", "output_path", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.pass_context
def main(ctx, only, force, pull_only, port_only, dry_run, output_format, output_path):
    token: str = (ctx.obj or {}).get("token", "")
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()

    repo, repo_path = require_repository()
    plan_path = artifact_path(repo_path, PLAN_FILE)
    status_path = artifact_path(repo_path, STATUS_FILE)

    # 1. Load plan.
    if not plan_path.exists():
        raise OopsError(f"No plan at {plan_path}. Run `oops migrate plan` first.")
    plan: MigrationPlan = load_plan(plan_path)

    # 2. Validate plan.
    outer: Result[None] = Result()
    _validate_plan(plan, outer)
    if not outer.ok:
        raise OopsError("Plan validation failed:\n" + "\n".join(f"  {e}" for e in outer.errors))

    # 3. Load status — verify prepare was done.
    migration = plan.migration
    apply_status = _load_status(status_path)
    if not dry_run and (apply_status is None or not apply_status.prepared):
        raise OopsError("Worktree not prepared. Run `oops migrate prepare --destination-ref <ref>` first.")

    # 4. Resolve worktree.
    wt_path = (
        Path(apply_status.worktree_path)
        if (apply_status and apply_status.worktree_path)
        else get_worktree_path(migration, repo_path)
    )
    dest_branch = apply_status.dest_branch if apply_status and apply_status.dest_branch else get_dest_branch(migration)
    pull_branch = get_pull_branch(migration)
    source_ref = migration.get("source_ref", "HEAD")

    if not dry_run and not wt_path.exists():
        raise OopsError(f"Worktree not found at {wt_path}. Re-run `oops migrate prepare`.")

    # 5. Init status if needed.
    if apply_status is None:
        apply_status = ApplyStatus(
            version=plan.version,
            plan_source_ref=source_ref,
            from_version=migration.get("from", ""),
            to_version=migration.get("to", ""),
        )

    # 6. Topological order.
    graph = build_graph(plan.modules, {})
    ordered = _topo_sort(graph)

    # 7. Build work set with filters.
    only_set = {m.strip() for m in only.split(",")} if only else None

    work_port: list[str] = []
    work_pull: list[str] = []

    for name in ordered:
        mp = plan.modules[name]
        if only_set and name not in only_set:
            continue
        rec = apply_status.modules.get(name)
        if rec and rec.status == "done" and not force:
            continue
        if mp.action == "port" and not pull_only:
            work_port.append(name)
        elif mp.action == "pull" and not port_only:
            work_pull.append(name)
        elif mp.action == "drop" and not pull_only and not port_only:
            work_port.append(name)  # drops are lightweight, go with port pass

    if not work_port and not work_pull:
        raise OopsError("Nothing to apply — all selected modules are already done.")

    rows: list[list] = []

    # 8a. Execute port + drop modules (sequential, topological order).
    for name in work_port:
        mp = plan.modules[name]
        branch = mp.resolved_branch or resolve_branch(mp, plan.migration, plan.groups)
        tools_run: list[str] = []
        error: Optional[str] = None
        status: ModuleStatus = "pending"

        with live_progress(f"Applying {name} ({mp.action})…"):
            try:
                if mp.action == "port":
                    tools_run = _apply_port(
                        mp,
                        repo,
                        wt_path,
                        dest_branch,
                        source_ref,
                        branch,
                        plan.defaults,
                        dry_run,
                    )
                elif mp.action == "drop":
                    log.debug(f"{name}: drop — no branch, no tooling")
                status = "done"
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or "").strip()
                error = f"Tool failed: {exc.cmd} (exit {exc.returncode})" + (f"\n{stderr}" if stderr else "")
                outer.add_error(f"{name}: {error}")
                status = "failed"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                outer.add_error(f"{name}: {error}")
                status = "failed"

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
                ", ".join(tools_run) or "—",
                error or "—",
            ]
        )

    # 8b. Execute pull modules (batch on pull_branch).
    if work_pull:
        pull_mps = [(plan.modules[n], pull_branch) for n in work_pull]

        with live_progress(f"Applying {len(work_pull)} pull module(s) on {pull_branch!r}…"):
            try:
                batch_results = _apply_pull_batch(
                    pull_mps, repo, wt_path, dest_branch, pull_branch, migration.get("to", ""), dry_run, token
                )
            except Exception as exc:  # noqa: BLE001
                batch_results = [(mp.name, "failed", [], str(exc)) for mp, _ in pull_mps]

        for name, status, tools_run, error in batch_results:
            if error:
                outer.add_error(f"{name}: {error}")
            apply_status.modules[name] = ModuleRecord(
                name=name,
                action="pull",
                branch=pull_branch,
                status=status,
                tools_run=tools_run,
                error=error,
                applied_at=datetime.now(UTC).isoformat() if not dry_run else None,
            )
            rows.append([name, "pull", pull_branch, status, "—", error or "—"])

        if not dry_run:
            _save_status(status_path, apply_status)

    # 9. Report.
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
