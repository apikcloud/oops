# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: check.py — oops/commands/submodules/check.py

"""
Check all submodules for common issues.

Verifies path conventions, URL scheme, branch presence, deprecated repository
references, unused submodules (no symlink points to them), and broken symlinks.
Exits non-zero if any issue is found.
"""

import configparser
import logging

import click

from oops.commands.base import command
from oops.core.config import config
from oops.io.file import check_prefix, list_symlinks
from oops.services.git import get_local_repo, read_gitmodules
from oops.utils.net import parse_repository_url
from oops.utils.render import print_error, print_success


@command(name="check", help=__doc__)
def main():  # noqa: C901

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

    res = True

    gitmodules = read_gitmodules(repo)

    for submodule in repo.submodules:
        # Check if submodule is under correct path
        if not check_prefix(submodule.path, config.submodules.current_path):
            bad_paths.append((submodule.name, submodule.path))

        # Check if any symlink target mentions this path
        if not any(submodule.path in t for t in symlinks):
            unused.append((submodule.name, submodule.path))

        # Check if branch is set in .gitmodules
        # branch_name cen't be used because it returns master if not set
        section = f'submodule "{submodule.name}"'
        try:
            branch = gitmodules.get_value(section, "branch")
            logging.debug(f"{submodule.name}: branch = {branch!r}")
        except configparser.NoOptionError:
            missing_branches.append((submodule.name, submodule.path))

        scheme, owner, repository = parse_repository_url(submodule.url)
        repository_name = f"{owner}/{repository}"

        # Check URL scheme
        if config.submodules.force_scheme and config.submodules.force_scheme != scheme:
            malformed_urls.append((submodule.name, submodule.url))

        # Check deprecated repositories
        if repository_name in config.submodules.deprecated_repositories:
            deprecated_repos.append(
                (submodule.name, config.submodules.deprecated_repositories[repository_name])
            )

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

    # TODO: add check for PRs

    if res:
        print_success(
            f"All submodules are under {config.submodules.current_path} "
            f"and used by at least one symlink."
        )
        raise click.exceptions.Exit(0)
    else:
        raise click.UsageError("Submodule check failed. Please fix the above issues.")
