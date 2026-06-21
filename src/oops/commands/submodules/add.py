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
from oops.core.compat import Optional, Tuple
from oops.core.config import config
from oops.core.exceptions import AppAbort, OopsError
from oops.core.logger import live_progress
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import create_symlink, desired_path, ensure_parent
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, read_gitmodules, require_repository
from oops.services.github import list_remote_addons
from oops.utils.net import encode_url, parse_repository_url
from oops.utils.render import colorize, prompt_choices


def _build_plan(selected_paths: list[str]) -> Plan:
    """Build a Plan from pre-selected addon relative paths."""
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
            for p in sorted(selected_paths)
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
    required=True,
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
    token: str,
) -> None:
    repo, repo_path = require_repository()

    # Validate URL and normalise scheme
    try:
        _, owner, repo_name = parse_repository_url(url)
        if config.submodules.force_scheme:
            url = encode_url(url, config.submodules.force_scheme)
    except ValueError as exc:
        raise OopsError(str(exc)) from exc

    # PRE-STEP: fetch addon list from GitHub Trees API then determine selection
    with live_progress("Fetching addon list from GitHub…"):
        remote_addons = list_remote_addons(owner, repo_name, branch, token)

    if addons:
        requested = {a.strip() for a in addons.split(",") if a.strip()}
        not_found = requested - {Path(p).name for p in remote_addons}
        if not_found:
            raise OopsError(f"Addon(s) not found in repository: {', '.join(sorted(not_found))}")
        selected_paths = [p for p in remote_addons if Path(p).name in requested]
    elif force:
        selected_paths = list(remote_addons)
    else:
        available = set(remote_addons)
        chosen = prompt_choices("Select addon(s) to symlink: ", available, set())
        if chosen is None:
            raise AppAbort()
        selected_paths = list(chosen)

    # Compute submodule name and path (PR suffix = first selected addon, if any)
    suffix: Optional[str] = Path(selected_paths[0]).name if pull_request and selected_paths else None
    sub_name = desired_path(url, pull_request=pull_request, suffix=suffix)
    sub_path_str = desired_path(
        url, prefix=str(config.submodules.current_path), pull_request=pull_request, suffix=suffix
    )
    sub_path = repo_path / sub_path_str

    # Safety checks before any mutation
    if sub_path.exists():
        raise OopsError(f"Destination already exists: {sub_path_str}")
    git_modules_dir = repo_path / ".git" / "modules" / sub_name
    if git_modules_dir.exists():
        raise OopsError(f"Git module directory already exists: {git_modules_dir}")

    plan = _build_plan(selected_paths)

    # Submodule is added lazily on the first apply() call — only after confirmation.
    submodule_ready = [False]

    def apply(action: PlanAction) -> Tuple[str, bool]:
        if not submodule_ready[0]:
            ensure_parent(sub_path)
            try:
                repo.create_submodule(name=sub_name, path=sub_path_str, url=url, branch=branch)
            except GitCommandError as exc:
                raise OopsError(f"Failed to add submodule: {exc}") from exc
            gm = read_gitmodules(repo)
            gm.set_value(f'submodule "{sub_name}"', "branch", branch)
            gm.write()
            submodule_ready[0] = True

        addon_dir = sub_path / action.data["rel_path"]
        link_name = create_symlink(addon_dir, repo_path)
        if link_name:
            repo.index.add([str(repo_path / link_name)])
            return colorize("linked", "green"), True
        return colorize("skipped (exists)", "yellow"), False

    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Add submodule",
        force=force,
        select=False,  # selection already done in the pre-step above
        empty_message="No addons selected; nothing to do.",
    )

    if not no_commit:
        linked = result.data.metrics.get("success", 0) if result.data else 0
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
                symlinks=linked,
                skip_hooks=True,
                already_staged=True,
            )
        )
    else:
        outer.add_warning("Changes staged but not committed (--no-commit).")

    render_and_raise(result, outer)
