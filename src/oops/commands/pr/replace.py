# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: replace.py — src/oops/commands/pr/replace.py

"""Replace PR submodule(s) with their canonical upstream submodule.

For each pull-request submodule, resolves the open PR upstream, derives the
target branch from the PR base (e.g. OCA:17.0 → 17.0), and replaces the PR
submodule with the canonical upstream one, rewriting root symlinks.

Every check runs BEFORE confirmation — PR resolution, branch validity, and
addon availability upstream (via the GitHub API when the local content does
not already answer the question). The presented plan reflects verified facts:
a row is either ready to apply, ready-with-warnings (some addons missing
upstream), or blocked (with a reason). apply() performs no discovery.
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
from oops.services.github import find_pull_requests, list_remote_addons
from oops.utils.net import encode_url, get_public_repo_url, parse_repository_url
from oops.utils.render import colorize, warn_experimental

# ---------------------------------------------------------------------------
# Pre-verification — establish a full verdict per PR sub before any mutation
# ---------------------------------------------------------------------------


def _resolve_prs(pr_subs, token: str) -> "Tuple[List[Tuple], List[Tuple[str, str]]]":
    """Resolve the open upstream PR for each PR submodule.

    Returns a list of (sub, info) for subs with a resolved PR. Subs without a
    resolvable PR are recorded as blocked verdicts later (here we only keep
    resolvable ones; unresolved are surfaced by the caller).
    """
    enriched: "List[Tuple]" = []
    unresolved: "List[Tuple[str, str]]" = []  # (name, reason)
    for sub in pr_subs:
        try:
            canonical_url = get_public_repo_url(sub.url)
            try:
                fork_branch = sub.branch_name
            except Exception:
                fork_branch = ""
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
                unresolved.append((sub.name, "no open PR found upstream"))
        except Exception as exc:  # noqa: BLE001 — recorded as a blocked verdict
            unresolved.append((sub.name, f"error resolving PR ({exc})"))
    return enriched, unresolved


def _verify_sub(
    sub,
    info,
    repo,
    repo_path,
    branch_override: "Optional[str]",
    token: str,
) -> dict:
    """Build a full, verified verdict dict for one PR sub.

    Performs the GitHub addon probe only when the local content cannot answer.
    Never assumes presence: addons_ok / addons_missing are factual.
    """
    pr = info.resolved_pr
    raw_branch = branch_override or pr.base.split(":")[1]
    upstream_url = f"https://github.com/{pr.upstream}.git"
    if config.submodules.force_scheme:
        upstream_url = encode_url(upstream_url, config.submodules.force_scheme)
    new_name = desired_path(upstream_url, pull_request=False)
    new_path = desired_path(upstream_url, pull_request=False, prefix=str(config.submodules.current_path))

    # Addons currently symlinked from this PR sub.
    pr_sub_path = repo_path / str(sub.path)
    pr_addon_names = [
        link.name
        for link in repo_path.iterdir()
        if link.is_symlink() and str(link.resolve()).startswith(str(pr_sub_path))
    ]

    existing = {s.name: str(s.path) for s in repo.submodules}
    upstream_exists = new_name in existing

    verdict = {
        "sub_name": sub.name,
        "old_path": str(sub.path),
        "upstream_url": upstream_url,
        "new_name": new_name,
        "new_path": new_path,
        "actual_new_path": existing.get(new_name, new_path),
        "branch": raw_branch,
        "pr_url": pr.url,
        "pr_addon_names": pr_addon_names,
        "upstream_exists": upstream_exists,
        "addons_ok": [],
        "addons_missing": [],
        "needs_content_update": False,
        "kind": "available",
        "reason": "",
    }

    # Branch guard — blocked, not fatal (other subs may still proceed).
    if raw_branch == "master":
        verdict.update(kind="blocked", reason="target branch is 'master' (use --branch)")
        return verdict

    if upstream_exists:
        upstream_local = repo_path / verdict["actual_new_path"]
        on_disk = [n for n in pr_addon_names if (upstream_local / n).exists()]
        off_disk = [n for n in pr_addon_names if n not in on_disk]

        if not off_disk:
            # Case 1: everything already on disk — no API call.
            verdict["addons_ok"] = on_disk
        else:
            # Case 2: disk is insufficient — probe upstream branch via API.
            try:
                remote = {
                    p.split("/")[-1] for p in list_remote_addons(*_owner_repo(upstream_url), verdict["branch"], token)
                }
            except Exception as exc:  # noqa: BLE001
                verdict.update(kind="blocked", reason=f"could not verify upstream ({exc})")
                return verdict
            present_upstream = [n for n in off_disk if n in remote]
            verdict["addons_ok"] = on_disk + present_upstream
            verdict["addons_missing"] = [n for n in off_disk if n not in remote]
            # Local content is behind: must update it to fetch the missing addons.
            verdict["needs_content_update"] = bool(present_upstream)
    else:
        # New upstream — probe the branch to know what will be available.
        try:
            remote = {
                p.split("/")[-1] for p in list_remote_addons(*_owner_repo(upstream_url), verdict["branch"], token)
            }
        except Exception as exc:  # noqa: BLE001
            verdict.update(kind="blocked", reason=f"could not verify upstream ({exc})")
            return verdict
        verdict["addons_ok"] = [n for n in pr_addon_names if n in remote]
        verdict["addons_missing"] = [n for n in pr_addon_names if n not in remote]

    # All required addons missing → blocked (the replacement has no purpose).
    if pr_addon_names and not verdict["addons_ok"]:
        verdict.update(kind="blocked", reason="no required addon found upstream")

    return verdict


def _owner_repo(url: str) -> "Tuple[str, str]":
    _, owner, repo_name = parse_repository_url(url)
    return owner, repo_name


# ---------------------------------------------------------------------------
# Plan construction — one row per sub, blocked rows shown but not selectable
# ---------------------------------------------------------------------------


def _build_plan(verdicts: "List[dict]", unresolved: "List[Tuple[str, str]]") -> Plan:
    """Build the plan: available / blocked rows, all visible for confirmation."""
    actions: "List[PlanAction]" = []

    for v in verdicts:
        if v["kind"] == "blocked":
            detail = colorize(v["reason"], "red")
        else:
            bits = []
            bits.append(f"{v['actual_new_path']} @ {v['branch']}")
            bits.append("[exists]" if v["upstream_exists"] else "[new]")
            if v["needs_content_update"]:
                bits.append(colorize("· updates upstream content", "yellow"))
            if v["addons_ok"]:
                bits.append(f"· symlinks: {', '.join(sorted(v['addons_ok']))}")
            if v["addons_missing"]:
                bits.append(colorize(f"· missing: {', '.join(v['addons_missing'])}", "yellow"))
            detail = " ".join(bits)

        actions.append(
            PlanAction(
                label=v["sub_name"],
                new=v["new_name"],
                detail=detail,
                kind=v["kind"],  # "available" or "blocked"
                data=v,
            )
        )

    # Unresolved PR subs appear as blocked rows too (full transparency).
    for name, reason in unresolved:
        actions.append(PlanAction(label=name, new=None, detail=colorize(reason, "red"), kind="blocked"))

    return Plan(title="Planned PR replacements", actions=actions)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


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
def main(token: str, branch_override: "Optional[str]", no_commit: bool, force: bool) -> None:
    repo, repo_path = require_repository()
    submodules = list(require_submodules(repo))

    warn_experimental()

    pr_subs = [s for s in submodules if is_pull_request(s)]
    if not pr_subs:
        raise OopsError("No pull-request submodules found.")

    # --- Pre-verification: resolve PRs, then verify each sub fully ---
    with live_progress("Verifying pull requests and upstream availability…"):
        enriched, unresolved = _resolve_prs(pr_subs, token)
        verdicts = [_verify_sub(sub, info, repo, repo_path, branch_override, token) for sub, info in enriched]

    plan = _build_plan(verdicts, unresolved)

    # Nothing actionable at all? Surface why (blocked rows carry reasons).
    if not any(a.kind == "available" for a in plan.actions):
        # Still render the plan so the user sees the blocked reasons.
        log.debug("No actionable replacement; all subs blocked or unresolved.")

    sub_map = {sub.name: sub for sub, _ in enriched}
    existing_sub_paths = {s.name: str(s.path) for s in repo.submodules}
    outer: Result = Result()

    def apply(action: PlanAction) -> "Tuple[str, bool]":
        v = action.data
        sub = sub_map[action.label]
        new_name = v["new_name"]
        old_path = v["old_path"]
        branch = v["branch"]
        actual_new_path = v["actual_new_path"]

        # 1. Remove PR submodule.
        sub.remove(force=True)

        # 2. Add upstream, or update content if behind, or leave as-is.
        if v["upstream_exists"] or new_name in existing_sub_paths:
            if v["needs_content_update"]:
                # Local upstream is behind: fetch the branch content so the
                # required addons become available before symlinking.
                log.debug(f"{new_name}: updating content to {branch}")
                repo.git.config(f"submodule.{new_name}.branch", branch)
                repo.git.submodule("update", "--remote", actual_new_path)
        else:
            ensure_parent(repo_path / actual_new_path)
            # --force reuses an existing .git/modules/<name> dir left by a prior remove.
            repo.git.submodule("add", "--force", "--name", new_name, "-b", branch, v["upstream_url"], actual_new_path)
            existing_sub_paths[new_name] = actual_new_path

        # 3. Initialise content (no-op if already initialised).
        repo.git.submodule("update", "--init", actual_new_path)

        # 4. Rewrite root symlinks old PR path → upstream path.
        rewrites = rewrite_symlinks(repo, [(old_path, actual_new_path)])

        # No post-init discovery: addon availability was verified beforehand.
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

    # Commit describes what actually succeeded, from the execution rows.
    if not no_commit:
        succeeded = [row for row in (result.data.rows if result.data else []) if "→" in str(row[1])]
        if succeeded:
            description = "\n".join(f"- replaced '{row[0]}'" for row in succeeded)
            outer.merge(
                commit_v2(
                    repo, repo_path, [], "pr_replace", description=description, skip_hooks=True, already_staged=True
                )
            )
    else:
        outer.add_warning("Changes staged but not committed (--no-commit).")

    render_and_raise(result, outer)
