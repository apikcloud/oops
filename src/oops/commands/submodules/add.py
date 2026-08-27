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
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import desired_path
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, require_repository
from oops.services.github import list_remote_addons
from oops.services.submodule import add_submodule
from oops.utils.net import encode_url, parse_repository_url
from oops.utils.render import colorize
from oops_engine.compat import Optional, Tuple

# Kind markers for the plan actions.
KIND_SUBMODULE = "add-submodule"
KIND_PR = "add-pr"
KIND_ADDON = "available"  # selectable by the workflow


def _build_plan(remote_addons: list[str], pull_request: bool) -> Plan:
    """Build the plan: a submodule placeholder + every addon as selectable.

    The submodule action carries no final name yet — it is resolved in
    `on_selected`, once the user's addon selection is known (the first
    selected addon drives the PR submodule name).
    """
    submodule = PlanAction(
        label="(submodule)",  # placeholder, resolved in on_selected
        new=None,
        detail="resolved after selection",
        kind=KIND_PR if pull_request else KIND_SUBMODULE,
        data={"is_submodule": True},
    )
    addons = [
        PlanAction(
            label=Path(p).name,
            new=None,
            detail=p,
            kind=KIND_ADDON,
            data={"rel_path": p},
        )
        for p in sorted(remote_addons)
    ]
    return Plan(title="Add submodule", actions=[submodule, *addons])


def add_submodule_flow(  # noqa: PLR0913, C901
    *,
    repo,
    repo_path: Path,
    url: str,
    branch: str,
    addons: Optional[str],
    no_commit: bool,
    force: bool,
    pull_request: bool,
    token: str,
    commit_message_name: str = "submodule_add",
    extra_commit_kwargs: Optional[dict] = None,
) -> None:
    """Core add-submodule logic shared by `submodules add` and `pr add`."""
    # Validate URL and normalise scheme
    try:
        _, owner, repo_name = parse_repository_url(url)
        if config.submodules.force_scheme:
            url = encode_url(url, config.submodules.force_scheme)
    except ValueError as exc:
        raise OopsError(str(exc)) from exc

    # Fetch addon list from the GitHub Trees API
    with live_progress("Fetching addon list from GitHub…"):
        remote_addons = list_remote_addons(owner, repo_name, branch, token)

    # Pre-restrict via --addons (validation only; selection stays in the workflow)
    if addons:
        requested = {a.strip() for a in addons.split(",") if a.strip()}
        not_found = requested - {Path(p).name for p in remote_addons}
        if not_found:
            raise OopsError(f"Addon(s) not found in repository: {', '.join(sorted(not_found))}")
        remote_addons = [p for p in remote_addons if Path(p).name in requested]

    plan = _build_plan(remote_addons, pull_request)

    # If addons were given explicitly, pre-select them so the workflow doesn't prompt.
    if addons:
        for action in plan.actions:
            if action.kind == KIND_ADDON:
                action.kind = "selected"

    # Mutable holder for the resolved submodule identity (filled in on_selected).
    ctx: dict = {}
    linked_names: list = []

    def on_selected(plan: Plan) -> None:
        """Resolve submodule name/path from the selection, then safety-check.

        Runs after selection, before presentation/confirmation, so the user
        sees the real submodule name and conflicts abort before any mutation.
        """
        selected_addons = [a for a in plan.actionable if a.data.get("rel_path")]
        suffix = Path(selected_addons[0].data["rel_path"]).name if (pull_request and selected_addons) else None
        sub_name = desired_path(url, pull_request=pull_request, suffix=suffix)
        sub_path_str = desired_path(
            url,
            prefix=str(config.submodules.current_path),
            pull_request=pull_request,
            suffix=suffix,
        )
        sub_path = repo_path / sub_path_str

        # Safety checks — before confirmation, before any mutation.
        if sub_path.exists():
            raise OopsError(f"Destination already exists: {sub_path_str}")
        git_modules_dir = repo_path / ".git" / "modules" / sub_name
        if git_modules_dir.exists():
            raise OopsError(f"Git module directory already exists: {git_modules_dir}")

        ctx.update(name=sub_name, path_str=sub_path_str, path=sub_path)

        # Fill the submodule action so the presented plan shows the real name.
        sub_action = next(a for a in plan.actionable if a.data.get("is_submodule"))
        sub_action.label = sub_name
        sub_action.new = branch
        sub_action.detail = sub_path_str

    outer: Result[None] = Result()

    def apply(action: PlanAction) -> Tuple[str, bool]:
        if action.data.get("is_submodule"):
            # Collect the selected addon rel_paths from the (post-selection) plan.
            sel_rels = [a.data["rel_path"] for a in plan.actionable if not a.data.get("is_submodule")]
            # Delegate creation + symlinking to the service; commit handled below.
            res = add_submodule(
                repo=repo, repo_path=repo_path, url=url, branch=branch,
                addons=None,
                pull_request=pull_request, token=token,
                no_commit=True,
                remote_addons=sel_rels,
            )
            outer.merge(res)
            linked_names.extend(res.data or [])
            return colorize("added", "green"), True

        # Addon action — already handled atomically by the service above.
        addon_name = Path(action.data["rel_path"]).name
        if addon_name in linked_names:
            return colorize("linked", "green"), True
        return colorize("skipped (exists)", "yellow"), False

    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Add submodule",
        force=force,
        select=True,
        select_prompt="Select addon(s) to symlink: ",
        on_selected=on_selected,
        empty_message="Nothing to do.",
    )

    if not no_commit:
        commit_kwargs = {
            "name": ctx.get("name", ""),
            "url": url,
            "branch": branch,
            "path": ctx.get("path_str", ""),
            "symlinks": len(linked_names),
        }
        if extra_commit_kwargs:
            commit_kwargs.update(extra_commit_kwargs)
        outer.merge(
            commit_v2(
                repo,
                repo_path,
                [],
                commit_message_name,
                skip_hooks=True,
                already_staged=True,
                **commit_kwargs,
            )
        )
    else:
        outer.add_warning("Changes staged but not committed (--no-commit).")

    render_and_raise(result, outer)


@command(name="add", help=__doc__)
@click.option("--addons", help="Comma-separated addon names to symlink (skips interactive prompt)")
@click.option("--no-commit", is_flag=True, help="Stage changes but do not commit")
@click.option("-f", "--force", is_flag=True, help="Apply without prompting, symlink all addons")
@click.option("--pull-request", is_flag=True, help="Treat as a pull-request submodule")
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token for API access (or set GH_TOKEN / GITHUB_TOKEN).",
    required=True,
)
@click.argument("url")
@click.argument("branch")
def main(
    url: str,
    branch: str,
    addons: Optional[str],
    no_commit: bool,
    force: bool,
    pull_request: bool,
    token: str,
) -> None:
    repo, repo_path = require_repository()
    add_submodule_flow(
        repo=repo,
        repo_path=repo_path,
        url=url,
        branch=branch,
        addons=addons,
        no_commit=no_commit,
        force=force,
        pull_request=pull_request,
        token=token,
    )
