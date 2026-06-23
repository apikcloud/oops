# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: replace.py — src/oops/commands/pr/replace.py

"""Replace PR submodule(s) with their canonical upstream submodule.

For each pull-request submodule (under .third-party/PRs/), resolves the open
PR on the upstream repository, derives the target branch from the PR base field
(e.g. OCA:17.0 → 17.0), adds or updates the upstream submodule, and rewrites
any root symlinks that pointed to the old PR path to point to the new one.
"""

from __future__ import annotations

import click
from oops.commands.base import command
from oops.core.compat import Optional, Tuple
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress, log
from oops.core.models import Plan, PlanAction, Result, SubmoduleInfo
from oops.io.file import desired_path, ensure_parent, rewrite_symlinks
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.services.github import find_pull_requests
from oops.utils.net import encode_url, get_public_repo_url, parse_repository_url
from oops.utils.render import colorize


def _build_plan(
    sub_pairs: "list[Tuple]",
    branch_override: "Optional[str]",
) -> Plan:
    """Build a pure-data plan from enriched (sub, info) pairs."""
    actions = []
    for sub, info in sub_pairs:
        pr = info.resolved_pr
        raw_branch = branch_override or pr.base.split(":")[1]
        upstream_url = f"https://github.com/{pr.upstream}.git"
        if config.submodules.force_scheme:
            upstream_url = encode_url(upstream_url, config.submodules.force_scheme)
        new_name = desired_path(upstream_url, pull_request=False)
        new_path = desired_path(
            upstream_url,
            pull_request=False,
            prefix=str(config.submodules.current_path),
        )
        pr_sub_path = str(sub.path)
        actions.append(
            PlanAction(
                label=sub.name,
                new=new_name,
                detail=f"{new_path} @ {raw_branch}",
                kind="available",
                data={
                    "old_path": pr_sub_path,
                    "upstream_url": upstream_url,
                    "new_name": new_name,
                    "new_path": new_path,
                    "branch": raw_branch,
                    "pr_url": pr.url,
                    "pr_addon_names": [],  # filled by main() after repo_path is known
                },
            )
        )
    return Plan(title="Planned PR replacements", actions=actions)


@command("replace", help=__doc__)
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    required=True,
    help="GitHub Personal Access Token (or set GH_TOKEN / GITHUB_TOKEN).",
)
@click.option(
    "--branch",
    "branch_override",
    default=None,
    metavar="BRANCH",
    help="Override target branch (default: derived from PR base).",
)
@click.option("--no-commit", is_flag=True, help="Stage changes but do not commit.")
@click.option("-f", "--force", is_flag=True, help="Apply without prompting.")
def main(
    token: str,
    branch_override: "Optional[str]",
    no_commit: bool,
    force: bool,
) -> None:
    repo, repo_path = require_repository()
    submodules = list(require_submodules(repo))

    pr_subs = [s for s in submodules if is_pull_request(s)]
    if not pr_subs:
        raise OopsError("No pull-request submodules found.")

    enriched: "list[Tuple]" = []
    with live_progress("Fetching pull requests…"):
        for sub in pr_subs:
            try:
                canonical_url = get_public_repo_url(sub.url)
                try:
                    fork_branch = sub.branch_name
                except Exception:
                    fork_branch = ""
                log.debug(f"PR sub {sub.name}: fork_branch={fork_branch}")
                _, fork_owner, fork_repo = parse_repository_url(canonical_url)
                prs = find_pull_requests(fork_owner, fork_repo, fork_branch, token=token)
                info = SubmoduleInfo(
                    name=sub.name,
                    url=canonical_url,
                    branch=fork_branch,
                    pull_request=True,
                    last_commit=None,
                    pull_requests=prs or [],
                )
                if info.resolved_pr:
                    enriched.append((sub, info))
                else:
                    log.warning(f"{sub.name}: no open PR found on upstream — skipped.")
            except Exception as exc:
                log.warning(f"{sub.name}: error resolving PR ({exc}) — skipped.")

    if not enriched:
        raise OopsError("No resolved pull requests found.")

    # Guard against master branch
    for sub, info in enriched:
        pr = info.resolved_pr
        effective_branch = branch_override or pr.base.split(":")[1]
        if effective_branch == "master":
            raise OopsError(
                f"{sub.name}: target branch is 'master'. "
                "Use --branch to specify a non-master branch."
            )

    plan = _build_plan(enriched, branch_override)

    # Fill in pr_addon_names now that repo_path is available
    for action in plan.actions:
        pr_sub_path = repo_path / action.data["old_path"]
        addon_names = [
            link.name
            for link in repo_path.iterdir()
            if link.is_symlink()
            and str(link.resolve()).startswith(str(pr_sub_path))
        ]
        action.data["pr_addon_names"] = addon_names
        log.debug(f"Plan action {action.label}: pr_addon_names={addon_names}")

    log.debug(
        f"Plan: {len(plan)} actions, target branches: "
        f"{set(a.data['branch'] for a in plan.actions)}"
    )

    sub_map = {sub.name: sub for sub, _ in enriched}
    outer: Result = Result()

    def apply(action: PlanAction) -> "Tuple[str, bool]":
        sub = sub_map[action.label]
        sub.remove(force=True)
        return colorize("removed", "red"), True

    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="PR Replacements",
        force=force,
        select=True,
        select_prompt="Select PR(s) to replace with upstream: ",
        empty_message="Nothing to replace.",
    )

    # Add or update upstream submodules, track old→new path pairs
    moved: "list[Tuple[str, str]]" = []
    sub_names = {s.name for s in repo.submodules}

    for action in plan.actionable:
        new_name = action.data["new_name"]
        new_path = action.data["new_path"]
        upstream_url = action.data["upstream_url"]
        branch = action.data["branch"]
        old_path = action.data["old_path"]
        pr_addon_names = action.data.get("pr_addon_names", [])

        if new_name in sub_names:
            actual_new_path = str(repo.submodules[new_name].path)
            upstream_local_path = repo_path / actual_new_path
            missing = [
                name for name in pr_addon_names
                if not (upstream_local_path / name).exists()
            ]
            if missing:
                log.debug(f"{new_name}: missing addons {missing}, updating branch to {branch}")
                repo.git.config(f"submodule.{new_name}.branch", branch)
            else:
                log.debug(f"{new_name}: all required addons present, branch unchanged")
        else:
            log.debug(f"Adding upstream submodule {new_name} at {new_path} branch={branch}")
            ensure_parent(repo_path / new_path)
            repo.git.submodule("add", "--name", new_name, "-b", branch, upstream_url, new_path)
            actual_new_path = new_path

        moved.append((old_path, actual_new_path))

    log.debug(f"Rewriting symlinks: {moved}")
    rewrites = rewrite_symlinks(repo, moved)
    outer.add_message(f"Symlinks rewritten: {rewrites}")

    if not no_commit:
        actions_by_label = {a.label: a for a in plan.actionable}
        description = "\n".join(
            f"- replaced '{lbl}' → '{actions_by_label[lbl].data['new_name']}'"
            f" (branch={actions_by_label[lbl].data['branch']})"
            for lbl in actions_by_label
        )
        outer.merge(
            commit_v2(
                repo,
                repo_path,
                [],
                "pr_replace",
                description=description,
                skip_hooks=True,
                already_staged=True,
            )
        )
    else:
        outer.add_warning("Changes staged but not committed (--no-commit).")

    render_and_raise(result, outer)
