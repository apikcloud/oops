#!/usr/bin/env python3

import configparser
import logging

import click
from git import Repo

from oops.core.config import config
from oops.utils.git import read_gitmodules
from oops.utils.io import check_prefix, list_symlinks
from oops.utils.net import parse_repository_url


@click.command(name="check")
def main():  # noqa: C901
    """
    Check git submodules for common issues
    """

    repo = Repo()

    if not repo.submodules:
        click.echo("No submodules found.")
        return 0

    symlinks = list_symlinks(repo.working_dir)
    broken_symlinks = list_symlinks(repo.working_dir, broken_only=True)
    bad_paths = []
    unused = []
    missing_branches = []
    malformed_urls = []
    deprecated_repos = []

    res = True

    gitmodules = read_gitmodules(repo)

    for submodule in repo.submodules:
        # Check if submodule is under correct path
        if not check_prefix(submodule.path, config.new_submodule_path):
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
        if config.sub_force_scheme and config.sub_force_scheme != scheme:
            malformed_urls.append((submodule.name, submodule.url))

        # Check deprecated repositories
        if repository_name in config.sub_deprecated_repositories:
            deprecated_repos.append(
                (submodule.name, config.sub_deprecated_repositories[repository_name])
            )

    if "check_path" in config.sub_checks and bad_paths:
        click.echo(f"❌ Submodules not under {config.new_submodule_path} ({len(bad_paths)}):")
        for name, path in bad_paths:
            click.echo(f"  - {name}: {path}")
        res = False

    if "check_symlink" in config.sub_checks and unused:
        click.echo("❌ Unused submodules (no symlink points to them):")
        for name, path in unused:
            click.echo(f"  - {name}: {path}")
        res = False

    if "check_branch" in config.sub_checks and missing_branches:
        click.echo("❌ Submodules without branch set in .gitmodules:")
        for name, path in missing_branches:
            click.echo(f"  - {name}: {path}")
        res = False

    if "check_url_scheme" in config.sub_checks and malformed_urls:
        click.echo(f"❌ Submodules with malformed URL (not {config.sub_force_scheme}):")
        for name, url in malformed_urls:
            click.echo(f"  - {name}: {url}")
        res = False

    if "check_deprecated_repo" in config.sub_checks and deprecated_repos:
        click.echo("❌ Submodules using deprecated repositories:")
        for name, repo in deprecated_repos:
            click.echo(f"  - {name}: must be replaced with {repo}")
        res = False

    if "check_broken_symlink" in config.sub_checks and broken_symlinks:
        click.echo("❌ Broken symlinks found:")
        for symlink in broken_symlinks:
            click.echo(f"  - {symlink}")
        res = False

    if res:
        click.echo(
            f"✅ All submodules are under {config.new_submodule_path} "
            f"and used by at least one symlink."
        )
        return 0
    else:
        return 1
