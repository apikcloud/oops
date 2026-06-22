# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: fix.py — oops/commands/submodules/fix.py

"""
Fix common submodule issues detected by submodules check.

Normalises submodule URLs to the configured scheme (e.g. SSH).
Deprecated repository replacements are reported but not applied
automatically — use ``oops submodules replace`` for those.
"""

import click
from oops.commands.base import command
from oops.core.compat import Tuple
from oops.core.config import config
from oops.core.models import Plan, PlanAction, Result
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, require_repository, require_submodules
from oops.utils.net import _parse_url, encode_url
from oops.utils.render import colorize


def _build_plan(submodules) -> Plan:
    """Build the URL-fix plan as pure data — no prompts, no colours."""
    actions = []
    for submodule in submodules:
        scheme, *_ = _parse_url(submodule.url)
        needs_fix = bool(config.submodules.force_scheme) and config.submodules.force_scheme != scheme
        actions.append(
            PlanAction(
                label=submodule.name,
                new=encode_url(submodule.url, config.submodules.force_scheme) if needs_fix else None,
                detail=f"{scheme} → {config.submodules.force_scheme}" if needs_fix else "",
                kind="available" if needs_fix else "nothing to do",
                data={"path": submodule.path},
            )
        )
    return Plan(title="Planned URL fixes", actions=actions)


@command(name="fix", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit automatically at the end.")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting.")
def main(no_commit: bool, force: bool) -> None:

    repo, repo_path = require_repository()
    submodules = require_submodules(repo)

    outer: Result[None] = Result()

    # Deprecated repos are not fixable by this command — report as warnings.
    for submodule in submodules:
        _, _, owner, repository = _parse_url(submodule.url)
        repository_name = f"{owner}/{repository}"
        if repository_name in config.submodules.deprecated_repositories:
            replacement = config.submodules.deprecated_repositories[repository_name]
            outer.add_warning(f"{submodule.name}: deprecated (→ {replacement}), use oops-sub-replace")

    # 1. Build the plan (pure business logic)
    plan = _build_plan(submodules)

    # 2. Define how to execute one action
    def apply(action: PlanAction) -> Tuple[str, bool]:
        repo.git.submodule("set-url", str(action.data["path"]), action.new)
        return colorize("fixed", "green"), True

    # 3. Run the shared scenario (select → present → confirm → apply)
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="URL fixes",
        force=force,
        select_prompt="Select submodule(s) to fix: ",
        empty_message="No URL issues found.",
    )

    # 4. Command-specific side effect: commit
    if not no_commit:
        description = "\n".join(f"- {a.label}: {a.new}" for a in plan.actionable)
        outer.merge(commit_v2(repo, repo_path, [".gitmodules"], "submodules_fix_urls", description=description))
    else:
        outer.add_warning("Don't forget to commit .gitmodules to share changes with the team.")

    # 5. Final render (after commit), non-zero exit on errors
    render_and_raise(result, outer)
