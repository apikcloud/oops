# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: github.py — oops/commands/misc/github.py

"""
Create a new GitHub repository from a template and clone it locally.

Prompts for a project name, slugifies it, asks for confirmation, then
delegates to the gh CLI to create the repository and optionally trigger
a workflow_dispatch event on a separate "action repository".

Reads default template, owner, visibility, and action settings from
github in ~/.oops.yaml. All values can be overridden with CLI options.

Requires gh to be authenticated (run 'gh auth login' if needed).
"""

import click
from oops.commands.base import command
from oops.core.config import config
from oops.services.github import check_gh, gh
from oops.utils.compat import List
from oops.utils.helpers import slugify
from oops.utils.render import print_success, print_warning


def _expand_inputs(inputs: dict, slug: str, owner: str, full_name: str) -> List[str]:
    """Expand $NAME/$OWNER/$FULL_NAME placeholders in action_inputs and return -f flags."""
    replacements = {"$NAME": slug, "$OWNER": owner, "$FULL_NAME": full_name, "True": "true", "False": "false"}
    result = []
    for key, value in inputs.items():
        expanded = str(value)
        for placeholder, replacement in replacements.items():
            expanded = expanded.replace(placeholder, replacement)
        result += ["-f", f"{key}={expanded}"]
    return result


@command(name="new-project", help=__doc__)
@click.option("--no-clone", is_flag=True, help="Create the repo but do not clone it")
def main(no_clone: bool) -> None:

    check_gh()

    cfg = config.github

    if not cfg.template:
        raise click.UsageError("No template configured. Set github.template in ~/.oops.yaml.")
    if not cfg.owner:
        raise click.UsageError("No owner configured. Set github.owner in ~/.oops.yaml.")

    # Prompt for name → slugify → let user edit → confirm
    raw_name = click.prompt("Project name")
    slug = slugify(raw_name)
    if cfg.prefix:
        slug = f"{slugify(cfg.prefix)}-{slug}"

    if not slug:
        raise click.UsageError("Could not produce a valid slug from the given name.")

    slug = click.prompt("Repository name", default=slug)
    full_name = f"{cfg.owner}/{slug}"
    click.confirm(f"Create '{full_name}' from template '{cfg.template}'?", abort=True)

    # Create repository via gh
    cmd = ["repo", "create", full_name, "--template", cfg.template, f"--{cfg.visibility}"]
    cmd += ["--description", raw_name]
    if not no_clone:
        cmd.append("--clone")

    click.echo(f"[create] {full_name} from {cfg.template}…")
    gh(*cmd)
    print_success(f"Repository created: https://github.com/{full_name}")

    # Grant team push access directly via gh api
    if cfg.team:
        click.echo(f"[team] granting push access to '{cfg.team}'…")
        try:
            gh(
                "api",
                "--method",
                "PUT",
                "-H",
                "Accept: application/vnd.github+json",
                f"/orgs/{cfg.owner}/teams/{cfg.team}/repos/{full_name}",
                "-f",
                "permission=push",
            )
            print_success(f"Team '{cfg.team}' granted push access.")
        except click.ClickException as e:
            print_warning(f"Team access failed: {e.format_message()}")

    # Trigger post-create workflow on the action repository if configured
    if cfg.action_repo and cfg.action_workflow:
        wf_cmd = [
            "workflow",
            "run",
            cfg.action_workflow,
            "--repo",
            cfg.action_repo,
            "--ref",
            cfg.action_ref,
            *_expand_inputs(cfg.action_inputs, slug, cfg.owner, full_name),
        ]
        click.echo(f"[dispatch] {cfg.action_repo} / {cfg.action_workflow} @ {cfg.action_ref}")
        try:
            gh(*wf_cmd)
            print_success(f"Workflow '{cfg.action_workflow}' dispatched on {cfg.action_repo}.")
        except click.ClickException as e:
            print_warning(f"Workflow dispatch failed: {e.format_message()}")

    if not no_clone:
        print_success(f"Ready in ./{slug}")
