# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — oops/commands/submodules/check.py

"""
Check all submodules for common issues.

Verifies path conventions, URL scheme, branch presence, deprecated repository
references, unused submodules (no symlink points to them), broken symlinks,
and pull-request submodules not under the configured PR directory.
Exits non-zero if any issue is found.
"""

import configparser
import logging

import click

from oops.commands.base import command
from oops.core.config import config
from oops.io.file import check_prefix, list_symlinks
from oops.services.git import get_local_repo, is_pull_request, read_gitmodules
from oops.utils.net import _parse_url
from oops.utils.render import print_error, print_success, print_warning


@command(name="check", help=__doc__)
def main():  # noqa: C901, PLR0912, PLR0915

    repo, repo_path = get_local_repo()

    if not repo.submodules:
        print_success("No submodules found.")
        raise click.exceptions.Exit(0)

    symlinks = list_symlinks(repo_path)
    broken_symlinks = list_symlinks(repo_path, broken_only=True)
    bad_paths = []
    unused = []
    missing_branches = []
    malformed_urls = []
    deprecated_repos = []
    misplaced_prs = []
    pr_submodules = []

    res = True

    gitmodules = read_gitmodules(repo)

    for submodule in repo.submodules:
        # Check if submodule is under correct path
        if not check_prefix(str(submodule.path), str(config.submodules.current_path)):
            bad_paths.append((submodule.name, submodule.path))

        # Check if any symlink target mentions this path
        if not any(str(submodule.path) in t for t in symlinks):
            unused.append((submodule.name, submodule.path))

        # Check if branch is set in .gitmodules
        # branch_name cen't be used because it returns master if not set
        section = f'submodule "{submodule.name}"'
        try:
            branch = gitmodules.get_value(section, "branch")
            logging.debug(f"{submodule.name}: branch = {branch!r}")
        except configparser.NoOptionError:
            missing_branches.append((submodule.name, submodule.path))

        scheme, _, owner, repository = _parse_url(submodule.url)
        repository_name = f"{owner}/{repository}"

        # Check URL scheme
        if config.submodules.force_scheme and config.submodules.force_scheme != scheme:
            malformed_urls.append((submodule.name, submodule.url))

        # Check deprecated repositories
        if repository_name in config.submodules.deprecated_repositories:
            deprecated_repos.append(
                (submodule.name, config.submodules.deprecated_repositories[repository_name])
            )

        # Track PR submodules
        if is_pull_request(submodule):
            pr_submodules.append((submodule.name, submodule.path))
            if not check_prefix(str(submodule.path), str(config.pull_request_dir)):
                misplaced_prs.append((submodule.name, submodule.path))

    if "check_path" in config.submodules.checks and bad_paths:
        print_error(f"Submodules not under {config.submodules.current_path} ({len(bad_paths)}):")
        for name, path in bad_paths:
            click.echo(f"  - {name}: {path}")
        res = False

    if "check_symlink" in config.submodules.checks and unused:
        print_error("Unused submodules (no symlink points to them):")
        for name, path in unused:
            click.echo(f"  - {name}: {path}")
        res = False

    if "check_branch" in config.submodules.checks and missing_branches:
        print_error("Submodules without branch set in .gitmodules:")
        for name, path in missing_branches:
            click.echo(f"  - {name}: {path}")
        res = False

    if "check_url_scheme" in config.submodules.checks and malformed_urls:
        print_error(f"Submodules with malformed URL (not {config.submodules.force_scheme}):")
        for name, url in malformed_urls:
            click.echo(f"  - {name}: {url}")
        res = False

    if "check_deprecated_repo" in config.submodules.checks and deprecated_repos:
        print_error("Submodules using deprecated repositories:")
        for name, repo in deprecated_repos:
            click.echo(f"  - {name}: must be replaced with {repo}")
        res = False

    if "check_broken_symlink" in config.submodules.checks and broken_symlinks:
        print_error("Broken symlinks found:")
        for symlink in broken_symlinks:
            click.echo(f"  - {symlink}")
        res = False

    if pr_submodules:
        print_warning(f"{len(pr_submodules)} pull-request submodule(s) detected:")
        for name, path in pr_submodules:
            click.echo(f"  - {name}: {path}")

    if "check_pr" in config.submodules.checks and misplaced_prs:
        print_error(f"PR submodules not under {config.pull_request_dir}:")
        for name, path in misplaced_prs:
            click.echo(f"  - {name}: {path}")
        res = False

    if res:
        print_success(
            f"All submodules are under {config.submodules.current_path} "
            f"and used by at least one symlink."
        )
        raise click.exceptions.Exit(0)
    else:
        raise click.UsageError("Submodule check failed. Please fix the above issues.")
