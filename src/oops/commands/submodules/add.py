# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: add.py — oops/commands/submodules/add.py

"""
Add a git submodule and optionally create symlinks for its addons.

Clones the repository as a submodule under the base directory (default:
.third-party), records the tracked branch, and optionally creates symlinks at
the repo root for every addon found or for a specific list.
"""

import click
from git import GitCommandError
from oops.commands.base import command
from oops.core.config import config
from oops.io.file import create_symlink, desired_path, ensure_parent, find_addon_dirs
from oops.services.git import commit, get_local_repo, read_gitmodules
from oops.utils.helpers import str_to_list
from oops.utils.net import encode_url, parse_repository_url
from oops.utils.render import human_readable, print_error, print_success, print_warning, render_table


@click.argument("branch")
@click.argument("url")
@click.option(
    "--base-dir",
    default=lambda: config.submodules.current_path,
    help="Base dir for submodules (default: .third-party)",
)
@click.option(
    "--auto-symlinks",
    is_flag=True,
    help="Auto-create symlinks at repo root for each addon folder detected in the submodule",
)
@click.option(
    "--addons",
    help="Comma-separated list of addon names for which to create symlinks",
)
@click.option(
    "--no-commit",
    is_flag=True,
    help="Stage changes but do not commit automatically",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show planned actions only, make no changes",
)
@click.option(
    "--pull-request",
    is_flag=True,
    help="Indicates that the submodule is a pull request (affects naming and path)",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Skip confirmation prompt",
)
@command(name="add", help=__doc__)
def main(  # noqa: PLR0913
    url: str,
    branch: str,
    base_dir: str,
    addons: str,
    auto_symlinks: bool,
    no_commit: bool,
    dry_run: bool,
    pull_request: bool,
    yes: bool,
) -> None:
    addons_to_link = str_to_list(addons) if addons else []

    repo, repo_path = get_local_repo()

    # Validate URL and optionally normalise scheme
    try:
        parse_repository_url(url)
        if config.submodules.force_scheme:
            url = encode_url(url, config.submodules.force_scheme)
    except ValueError as e:
        print_error(str(e))
        raise click.exceptions.Exit(1) from e

    suffix = addons_to_link[0] if addons_to_link and pull_request else None
    sub_path_str = desired_path(url, prefix=base_dir, pull_request=pull_request, suffix=suffix)
    sub_path = repo_path / sub_path_str
    sub_name = desired_path(url, pull_request=pull_request, suffix=suffix)

    # Plan summary
    rows = [
        ["URL", url],
        ["Branch", branch],
        ["Submodule name", sub_name],
        ["Target path", sub_path_str],
        ["Auto symlinks", human_readable(auto_symlinks)],
        ["Addons", addons or ""],
        ["Commit at the end", human_readable(not no_commit)],
    ]
    click.echo(render_table(rows))

    if dry_run:
        print_warning("This is a dry run. No changes will be made.")
        raise click.Abort()

    if not yes and not click.confirm("Apply changes?", default=True):
        raise click.Abort()

    # Safety checks before touching anything
    if sub_path.exists():
        print_error(f"Destination already exists: {sub_path_str}")
        raise click.exceptions.Exit(1)

    git_modules_path = repo_path / ".git" / "modules" / sub_name
    if git_modules_path.exists():
        print_error(f"Git module directory already exists: {git_modules_path}")
        raise click.exceptions.Exit(1)

    ensure_parent(sub_path)

    # Add submodule
    click.echo("[add] git submodule add")
    try:
        repo.create_submodule(name=sub_name, path=sub_path_str, url=url, branch=branch)
    except GitCommandError as exc:
        print_error(f"Failed to add submodule: {exc}")
        raise click.exceptions.Exit(1) from exc

    # Pin branch in .gitmodules
    gitmodules = read_gitmodules(repo)
    click.echo(f"[config] setting branch {branch!r} for {sub_name!r}…")
    gitmodules.set_value(f'submodule "{sub_name}"', "branch", branch)

    # Create symlinks
    staged_files = []
    created_links = []

    if auto_symlinks or addons:
        click.echo("[scan] detecting addon folders…")
        addons_found = find_addon_dirs(sub_path, with_pr=pull_request)
        if not addons_found:
            click.echo("  no addon folders detected.")
        else:
            click.echo(f"  found {len(addons_found)} addon folder(s). Creating symlinks at repo root…")
            candidates = addons_found if auto_symlinks else [a for a in addons_found if a.name in addons_to_link]
            for addon_dir in candidates:
                link_name = create_symlink(addon_dir, repo_path)
                if link_name:
                    staged_files.append(link_name)
                    created_links.append(link_name)

        if addons:
            missing = set(addons_to_link) - set(created_links)
            if missing:
                print_warning(f"Addons not found: {human_readable(missing)}")

    staged_files += [".gitmodules"]

    print(staged_files)

    if not no_commit:
        commit(
            repo,
            repo_path,
            [str(repo_path / f) for f in staged_files],
            "submodule_add",
            name=sub_name,
            url=url,
            branch=branch,
            path=sub_path_str,
            symlinks=human_readable(created_links) if created_links else 0,
        )
        print_success("Submodule added and committed.")
    else:
        repo.index.add([str(repo_path / f) for f in staged_files])
        print_warning("Changes staged but not committed (--no-commit).")
