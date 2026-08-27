# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: manage.py — src/oops/commands/pr/manage.py

"""
Toggle submodules between pull-request and regular status.

Interactively select which submodules should be treated as pull requests.
Promoting or demoting recomputes the canonical name and path, renames and
moves the submodule accordingly, then rewrites any symlink that referenced
the moved path.
"""

from __future__ import annotations

import shutil

from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import AppAbort
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import desired_path, get_symlink_map, rewrite_symlinks
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize, prompt_choices
from oops_engine.compat import Tuple


def _build_plan(submodules, mapping, marked_as_pr: set[str]) -> Plan:
    """Build the promote/demote plan as pure data.

    `marked_as_pr` is the set of submodule names that should END UP as PRs.
    Any submodule whose PR status flips (and whose name/path changes as a
    result) becomes an actionable entry.
    """
    actions = []
    for submodule in submodules:
        currently_pr = is_pull_request(submodule)
        should_be_pr = submodule.name in marked_as_pr
        if currently_pr == should_be_pr:
            continue  # status unchanged → not part of the plan

        first_symlink = mapping.get(submodule.path) if should_be_pr else None
        new_name = desired_path(submodule.url, pull_request=should_be_pr, suffix=first_symlink)
        new_path = desired_path(
            submodule.url,
            prefix=str(config.submodules.current_path),
            pull_request=should_be_pr,
            suffix=first_symlink,
        )

        if submodule.name == new_name and str(submodule.path) == str(new_path):
            continue  # nothing concrete to do

        actions.append(
            PlanAction(
                label=submodule.name,
                new=new_name,
                detail=str(new_path),
                kind="promote" if should_be_pr else "demote",
                data={
                    "old_path": str(submodule.path),
                    "new_path": str(new_path),
                    "as_pr": should_be_pr,
                },
            )
        )
    return Plan(title="Planned renames + rewrites", actions=actions)


@command("manage", help=__doc__)
def main():
    repo, repo_path = require_repository()
    submodules = require_submodules(repo)

    available = {sub.name for sub in submodules}
    pull_requests = {sub.name for sub in submodules if is_pull_request(sub)}

    # Upstream selection: which submodules should be PRs after this command.
    selected = prompt_choices("Select pull request(s): ", available, pull_requests)
    if not selected:
        raise AppAbort()

    mapping = get_symlink_map(repo_path)

    # Build the plan from the desired PR set. Status flips drive the actions.
    plan = _build_plan(submodules, mapping, selected)

    # Execution of one action — records moved paths.
    sub_map = {s.name: s for s in submodules}
    moved: list[Tuple[str, str]] = []

    def apply(action: PlanAction) -> Tuple[str, bool]:
        sub = sub_map[action.label]
        sub.rename(action.new)
        if action.data["old_path"] != action.data["new_path"]:
            try:
                sub.move(action.data["new_path"])
            except Exception:
                sub.rename(action.label)  # undo rename to keep .gitmodules consistent
                raise
            moved.append((action.data["old_path"], action.data["new_path"]))
        return colorize("renamed + moved", "green"), True

    # Selection already happened upstream → disable the workflow's own prompt.
    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Renames + Rewrites",
        select=False,
        empty_message="Nothing to change.",
    )

    # Side effects: rewrite symlinks + clean old base dir
    rewrites = rewrite_symlinks(repo, moved)
    outer.add_message(f"Symlinks rewritten: {rewrites}")

    if config.submodules.old_paths[0].exists():
        shutil.rmtree(config.submodules.old_paths[0])
        repo.index.remove([str(config.submodules.old_paths[0])], r=True, f=True)
        outer.add_message(f"Removed old submodule base dir: {config.submodules.old_paths[0]}")

    # move() stages .gitmodules; stage it explicitly to also capture rename() changes.
    repo.index.add([".gitmodules"])
    outer.merge(commit_v2(repo, repo_path, [], "pr_manage", skip_hooks=True, already_staged=True))

    render_and_raise(result, outer)
