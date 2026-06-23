# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: replace.py — src/oops/commands/pr/replace.py

"""Replace PR submodule(s) with their canonical upstream submodule.

For each pull-request submodule (under .third-party/PRs/), resolves the open
PR on the upstream repository, derives the target branch from the PR base field
(e.g. OCA:17.0 → 17.0), adds or updates the upstream submodule, initializes
its content, and rewrites any root symlinks that pointed to the old PR path to
point to the new one.
"""

from __future__ import annotations

import click
from oops.commands.base import command
from oops.core.compat import List, Optional, Tuple
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


def _step(label: str, new: "Optional[str]" = None, detail: str = "") -> PlanAction:
    """Create a display-only step row (not executed, not selectable)."""
    return PlanAction(label=label, new=new, detail=detail, kind="step")


def _build_plan(sub_plans: "List[dict]") -> Plan:
    """Build a plan from pre-computed per-sub state dicts.

    Each PR sub generates one selectable "available" action row followed by
    "step" rows describing individual operations (remove, add/update, init,
    per-addon symlinks). Step rows are display-only — they appear in the plan
    table but are never passed to apply().
    """
    actions: "List[PlanAction]" = []
    for sp in sub_plans:
        new_name: str = sp["new_name"]
        actual_new_path: str = sp["actual_new_path"]
        branch: str = sp["branch"]

        # Main selectable row: PR sub → upstream, top-level summary.
        if sp["upstream_exists"]:
            detail = f"{actual_new_path} [exists, branch {branch}]"
        else:
            detail = f"{sp['new_path']} @ {branch} [new]"

        actions.append(
            PlanAction(
                label=sp["sub_name"],
                new=new_name,
                detail=detail,
                kind="available",
                data=sp,
            )
        )

        # Step rows: one per distinct operation, in execution order.
        actions.append(_step("  remove PR sub"))

        if sp["upstream_exists"]:
            if sp["needs_branch_update"]:
                actions.append(_step("  update branch", detail=f"→ {branch}"))
        else:
            actions.append(_step("  add upstream", new=new_name, detail=f"{sp['new_path']} @ {branch}"))

        actions.append(_step("  init content", detail=actual_new_path))

        for addon in sp["addons_ok"]:
            actions.append(_step(f"  {addon}", detail=f"symlink → {actual_new_path}"))

        for addon in sp["addons_missing"]:
            actions.append(_step(f"  {addon}", detail="missing in upstream"))

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

    enriched: "List[Tuple]" = []
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

    # Guard against master branch.
    for sub, info in enriched:
        pr = info.resolved_pr
        effective_branch = branch_override or pr.base.split(":")[1]
        if effective_branch == "master":
            raise OopsError(
                f"{sub.name}: target branch is 'master'. "
                "Use --branch to specify a non-master branch."
            )

    # Snapshot currently registered upstream subs (name → path).
    # Updated as new upstreams are added during apply() to handle multiple
    # PR subs resolving to the same upstream within a single run.
    existing_sub_paths: "dict[str, str]" = {s.name: str(s.path) for s in repo.submodules}

    # Pre-compute full per-sub state before building the plan so the plan
    # already reflects local reality (addon presence, branch state).
    sub_plans: "List[dict]" = []
    for sub, info in enriched:
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

        # Collect addons currently symlinked from this PR sub.
        pr_sub_path = repo_path / str(sub.path)
        pr_addon_names = [
            link.name
            for link in repo_path.iterdir()
            if link.is_symlink()
            and str(link.resolve()).startswith(str(pr_sub_path))
        ]
        log.debug(f"{sub.name}: pr_addon_names={pr_addon_names}")

        # Check addon presence in upstream if it already exists locally.
        upstream_exists = new_name in existing_sub_paths
        if upstream_exists:
            actual_new_path = existing_sub_paths[new_name]
            upstream_local = repo_path / actual_new_path
            addons_ok = [n for n in pr_addon_names if (upstream_local / n).exists()]
            addons_missing = [n for n in pr_addon_names if not (upstream_local / n).exists()]
            needs_branch_update = bool(addons_missing)
        else:
            actual_new_path = new_path
            # Content not yet available; assume all addons will be present after init.
            addons_ok = list(pr_addon_names)
            addons_missing = []
            needs_branch_update = False

        log.debug(
            f"{sub.name}: upstream_exists={upstream_exists}, "
            f"addons_ok={addons_ok}, addons_missing={addons_missing}"
        )

        sub_plans.append({
            "sub_name": sub.name,
            "old_path": str(sub.path),
            "upstream_url": upstream_url,
            "new_name": new_name,
            "new_path": new_path,
            "actual_new_path": actual_new_path,
            "branch": raw_branch,
            "pr_url": pr.url,
            "pr_addon_names": pr_addon_names,
            "upstream_exists": upstream_exists,
            "addons_ok": addons_ok,
            "addons_missing": addons_missing,
            "needs_branch_update": needs_branch_update,
        })

    plan = _build_plan(sub_plans)
    log.debug(
        f"Plan: {len(plan.actionable)} actionable, target branches: "
        f"{set(a.data['branch'] for a in plan.actionable)}"
    )

    sub_map = {sub.name: sub for sub, _ in enriched}
    outer: Result = Result()

    def apply(action: PlanAction) -> "Tuple[str, bool]":
        sp = action.data
        sub = sub_map[action.label]
        new_name = sp["new_name"]
        old_path = sp["old_path"]
        branch = sp["branch"]
        actual_new_path = sp["actual_new_path"]

        # 1. Remove PR submodule.
        sub.remove(force=True)

        # 2. Add or update upstream sub.
        # Re-check existing_sub_paths to handle multiple PR subs sharing an upstream.
        if sp["upstream_exists"] or new_name in existing_sub_paths:
            if sp["needs_branch_update"]:
                log.debug(f"{new_name}: updating branch to {branch}")
                repo.git.config(f"submodule.{new_name}.branch", branch)
            else:
                log.debug(f"{new_name}: already present, branch unchanged")
        else:
            log.debug(f"Adding upstream submodule {new_name} at {actual_new_path} branch={branch}")
            ensure_parent(repo_path / actual_new_path)
            repo.git.submodule(
                "add", "--name", new_name, "-b", branch, sp["upstream_url"], actual_new_path
            )
            existing_sub_paths[new_name] = actual_new_path

        # 3. Initialize and fetch upstream sub content.
        log.debug(f"Initializing submodule content at {actual_new_path}")
        repo.git.submodule("update", "--init", actual_new_path)

        # 4. Rewrite root symlinks that pointed into the old PR sub path.
        log.debug(f"Rewriting symlinks: {old_path!r} → {actual_new_path!r}")
        rewrites = rewrite_symlinks(repo, [(old_path, actual_new_path)])

        # 5. Post-init: warn for addons pre-identified as missing (existing sub)
        #    or absent after init (new sub, where we couldn't check beforehand).
        upstream_local = repo_path / actual_new_path
        for addon_name in sp["pr_addon_names"]:
            if not (upstream_local / addon_name).exists():
                outer.add_warning(
                    f"{new_name}: addon '{addon_name}' not found in upstream"
                    " — symlink may be stale."
                )

        label = f"→ {new_name} ({rewrites} symlink{'s' if rewrites != 1 else ''})"
        return colorize(label, "green"), True

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
