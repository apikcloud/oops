# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: add.py — oops/commands/submodules/add.py

"""
Add a git submodule and create symlinks for selected addons.

Queries the target repository via the GitHub Trees API to list its addon
directories (folders containing __manifest__.py or __openerp__.py), then
prompts for which addons to symlink at the repo root.

Usage:
    oops submodules add URL BRANCH [--pull-request] [--addons a,b] [--token TOKEN]
"""

from __future__ import annotations

from pathlib import Path

import click
from git import GitCommandError
from oops.commands.base import command
from oops.core.compat import Optional
from oops.core.config import config
from oops.core.exceptions import AppAbort, OopsError
from oops.core.logger import live_progress
from oops.core.models import Plan, PlanAction, Result, Rows
from oops.io.file import create_symlink, desired_path, ensure_parent
from oops.output.helper import render_and_raise, render_plan
from oops.services.git import commit_v2, read_gitmodules, require_repository
from oops.services.github import list_remote_addons
from oops.utils.net import encode_url, parse_repository_url
from oops.utils.render import colorize, prompt_choices, prompt_confirm


def _build_plan(selected_addons: list[str]) -> Plan:
    """Build a Plan from the list of addon relative paths chosen for symlinking."""
    return Plan(
        title="Addon symlinks",
        actions=[
            PlanAction(
                label=Path(p).name,
                new=None,
                detail=p,
                kind="selected",
                data={"rel_path": p},
            )
            for p in sorted(selected_addons)
        ],
    )


@command(name="add", help=__doc__)
@click.option("--addons", help="Comma-separated addon names to symlink (skips interactive prompt)")
@click.option("--no-commit", is_flag=True, help="Stage changes but do not commit")
@click.option("-f", "--force", is_flag=True, help="Apply without prompting, symlink all addons")
@click.option("--pull-request", is_flag=True, help="Treat as a pull-request submodule")
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token for API access (or set GH_TOKEN / GITHUB_TOKEN).",
)
@click.argument("url")
@click.argument("branch")
def main(  # noqa: PLR0912, PLR0913
    url: str,
    branch: str,
    addons: Optional[str],
    no_commit: bool,
    force: bool,
    pull_request: bool,
    token: Optional[str],
) -> None:
    repo, repo_path = require_repository()

    # Validate URL and normalise scheme
    try:
        _, owner, repo_name = parse_repository_url(url)
        if config.submodules.force_scheme:
            url = encode_url(url, config.submodules.force_scheme)
    except ValueError as exc:
        raise OopsError(str(exc)) from exc

    # Fetch addon list from GitHub Trees API
    with live_progress("Fetching addon list from GitHub…"):
        remote_addons = list_remote_addons(owner, repo_name, branch, token)

    # Determine which addons to symlink
    if addons:
        requested = {a.strip() for a in addons.split(",") if a.strip()}
        not_found = requested - {Path(p).name for p in remote_addons}
        if not_found:
            raise OopsError(f"Addon(s) not found in repository: {', '.join(sorted(not_found))}")
        selected_addons = [p for p in remote_addons if Path(p).name in requested]
    elif force:
        selected_addons = list(remote_addons)
    else:
        available = {p for p in remote_addons}
        if not available:
            click.echo("No addons detected in repository root; the submodule will be added without symlinks.")
            selected_addons = []
        else:
            chosen = prompt_choices("Select addon(s) to symlink: ", available, set())
            if chosen is None:
                raise AppAbort()
            selected_addons = list(chosen)

    # Build plan (only selected addons)
    plan = _build_plan(selected_addons)

    # Compute submodule name and path (PR suffix = first selected addon, if any)
    suffix: Optional[str] = None
    if pull_request and plan.actions:
        suffix = plan.actions[0].label
    sub_name = desired_path(url, pull_request=pull_request, suffix=suffix)
    sub_path_str = desired_path(
        url, prefix=str(config.submodules.current_path), pull_request=pull_request, suffix=suffix
    )
    sub_path = repo_path / sub_path_str

    # Safety checks before touching anything
    if sub_path.exists():
        raise OopsError(f"Destination already exists: {sub_path_str}")
    git_modules_dir = repo_path / ".git" / "modules" / sub_name
    if git_modules_dir.exists():
        raise OopsError(f"Git module directory already exists: {git_modules_dir}")

    # Show plan and confirm (even if no addons: plan is empty but still shows sub info)
    render_plan(plan)

    if not force and not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    # — Everything below runs only after explicit confirmation —

    ensure_parent(sub_path)

    try:
        repo.create_submodule(name=sub_name, path=sub_path_str, url=url, branch=branch)
    except GitCommandError as exc:
        raise OopsError(f"Failed to add submodule: {exc}") from exc

    # Pin branch in .gitmodules
    gitmodules = read_gitmodules(repo)
    gitmodules.set_value(f'submodule "{sub_name}"', "branch", branch)
    gitmodules.write()

    # Create symlinks
    outer: Result[None] = Result()
    rows_data = Rows(
        title="Addon symlinks",
        columns=[("Addon", "brand.primary", "left"), ("Status", "dim", "center")],
        rows=[],
        metrics={"total": len(plan.actions), "linked": 0, "skipped": 0},
    )
    result: Result[Rows] = Result(data=rows_data)

    for action in plan.actions:
        addon_dir = sub_path / action.data["rel_path"]
        link_name = create_symlink(addon_dir, repo_path)
        if link_name:
            repo.index.add([str(repo_path / link_name)])
            rows_data.rows.append([action.label, colorize("linked", "green")])
            rows_data.metrics["linked"] += 1
        else:
            rows_data.rows.append([action.label, colorize("skipped", "yellow")])
            rows_data.metrics["skipped"] += 1

    if not no_commit:
        outer.merge(
            commit_v2(
                repo,
                repo_path,
                [],
                "submodule_add",
                name=sub_name,
                url=url,
                branch=branch,
                path=sub_path_str,
                symlinks=rows_data.metrics["linked"],
                skip_hooks=True,
                already_staged=True,
            )
        )
    else:
        outer.add_warning("Changes staged but not committed (--no-commit).")

    render_and_raise(result, outer)
