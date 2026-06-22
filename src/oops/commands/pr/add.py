# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: add.py — oops/commands/pr/add.py

"""Add a pull-request submodule from a PR URL.

Resolves the pull request's head repository (fork) and branch, lists its addon
directories, and symlinks the selected ones — like ``oops submodules add`` but
driven by a PR URL instead of a repo URL + branch.

Usage:
    oops pr add https://github.com/OCA/mail/pull/4 [--addons a,b] [--token TOKEN]
"""

from __future__ import annotations

import click
from oops.commands.base import command
from oops.commands.submodules.add import add_submodule_flow
from oops.core.compat import Optional
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress
from oops.services.git import require_repository
from oops.services.github import get_pull_request
from oops.utils.net import parse_pull_request_url


@command(name="add", help=__doc__)
@click.option("--addons", help="Comma-separated addon names to symlink (skips interactive prompt)")
@click.option("--no-commit", is_flag=True, help="Stage changes but do not commit")
@click.option("-f", "--force", is_flag=True, help="Apply without prompting, symlink all addons")
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token for API access (or set GH_TOKEN / GITHUB_TOKEN).",
    required=True,
)
@click.argument("url")
def main(url: str, addons: Optional[str], no_commit: bool, force: bool, token: str) -> None:
    repo, repo_path = require_repository()

    try:
        pr_owner, pr_repo, number = parse_pull_request_url(url)
    except ValueError as exc:
        raise OopsError(str(exc)) from exc

    with live_progress("Fetching pull request from GitHub…"):
        pr = get_pull_request(pr_owner, pr_repo, number, token)

    if not pr.head_repo_url or not pr.head_ref:
        raise OopsError(f"PR #{number} head repository is unavailable (fork deleted?).")

    add_submodule_flow(
        repo=repo,
        repo_path=repo_path,
        url=pr.head_repo_url,
        branch=pr.head_ref,
        addons=addons,
        no_commit=no_commit,
        force=force,
        pull_request=True,
        token=token,
        commit_message_name="pr_add",
        extra_commit_kwargs={"pr_url": pr.url},
    )
