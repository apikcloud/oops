# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: rewrite.py — oops/commands/submodules/rewrite.py

"""
Move submodule paths under a canonical base directory and update symlinks.

Computes the target path for each submodule under the base directory (default:
.third-party), moves the submodule, and rewrites all symlinks that referenced
the old path. Prompts for confirmation unless --force is used.
"""

from __future__ import annotations

import shutil

import click
from git.exc import GitCommandError
from oops.commands.base import command
from oops.core.compat import Tuple
from oops.core.config import config
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import desired_path, get_symlink_map, rewrite_symlinks
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize


def _build_plan(submodules, mapping, base_dir) -> Plan:
    """Build the rewrite plan as pure data — no prompts, no colours."""
    actions = []
    for submodule in submodules:
        if not submodule.url or submodule.path not in mapping:
            actions.append(PlanAction(label=submodule.name, detail=str(submodule.path), kind="skipped"))
            continue

        pull_request = is_pull_request(submodule)
        first_symlink = mapping[submodule.path] if pull_request else None
        target = desired_path(submodule.url, prefix=base_dir, pull_request=pull_request, suffix=first_symlink)

        changed = str(submodule.path) != str(target)
        actions.append(
            PlanAction(
                label=submodule.name,
                new=str(target) if changed else None,
                detail=str(submodule.path),
                kind="available" if changed else "nothing to do",
                data={"old_path": str(submodule.path), "target": str(target)},
            )
        )
    return Plan(title="Planned rewrites", actions=actions)


@command(name="rewrite", help=__doc__)
@click.option(
    "--base-dir",
    default=lambda: config.submodules.current_path,
    help="Base directory for rewritten paths (default: .third-party)",
)
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.option("--no-commit", is_flag=True, help="Do not commit automatically at the end")
@click.argument("names", nargs=-1, required=False)
def main(base_dir, force: bool, no_commit: bool, names: Tuple[str, ...]):
    repo, repo_path = require_repository()
    submodules = require_submodules(repo)
    mapping = get_symlink_map(repo_path)

    # 1. Build the plan
    plan = _build_plan(submodules, mapping, base_dir)

    # 2. Narrow by CLI names
    if names:
        plan.restrict_to(set(names))

    # 3. Execution of one action — records moved paths as a side effect
    sub_map = {s.name: s for s in submodules}
    moved: list[Tuple[str, str]] = []

    def apply(action: PlanAction) -> Tuple[str, bool]:
        sub = sub_map[action.label]
        sub.move(action.data["target"])
        moved.append((action.data["old_path"], action.data["target"]))
        return colorize("moved", "green"), True

    # 4. Run the shared scenario
    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Rewrites",
        force=force,
        select_prompt="Select submodule(s) to rewrite: ",
        empty_message="No submodule needs rewriting.",
    )

    # 5. Command-specific side effects: rewrite symlinks + clean old base dir
    rewrites = rewrite_symlinks(repo, moved)
    outer.add_message(f"Symlinks rewritten: {rewrites}")

    if config.submodules.old_paths[0].exists():
        shutil.rmtree(config.submodules.old_paths[0])
        try:
            repo.index.remove([str(config.submodules.old_paths[0])], r=True, f=True)
        except GitCommandError:
            pass  # path not in index — filesystem removal is sufficient
        outer.add_message(f"Removed old submodule base dir: {config.submodules.old_paths[0]}")

    # 6. Commit
    if not no_commit and repo.index.diff(repo.head.commit):
        outer.merge(commit_v2(repo, repo_path, [], "submodules_rewrite", skip_hooks=True, already_staged=True))
    elif no_commit:
        outer.add_warning("Changes staged but not committed (--no-commit).")

    # 7. Final render
    render_and_raise(result, outer)
