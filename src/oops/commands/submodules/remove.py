# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: remove.py — oops/commands/submodules/remove.py

"""
Remove one or more submodules and their associated symlinks.

When called without arguments, displays an indexed menu of all submodules.
Enter the index numbers (comma-separated) to select which to remove.
Submodule names can also be passed directly as arguments.

Associated symlinks pointing into the removed submodule paths are removed
automatically. Prompts for confirmation before applying any changes.
"""

import os
from pathlib import Path

import click
from oops.commands.base import command
from oops.services.git import commit, get_local_repo
from oops.utils.render import print_success, print_warning, render_table


@command("remove", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.argument("names", nargs=-1, required=False)
def main(dry_run: bool, no_commit: bool, force: bool, names: tuple):  # noqa: C901

    repo, repo_path = get_local_repo()

    if not repo.submodules:
        raise click.UsageError("No submodules found.")

    submodules = list(repo.submodules)

    if not names:
        # Display indexed menu and prompt for selection
        rows = [[sub.name, sub.url, sub.path] for sub in submodules]
        click.echo(render_table(rows, headers=["Name", "URL", "Path"], index=True))
        raw = click.prompt("\nEnter index(es) to remove (comma-separated, empty to abort)", default="")
        if not raw.strip():
            raise click.Abort()

        selected = []
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                idx = int(token)
            except ValueError as error:
                raise click.UsageError(f"Invalid index: {token!r}") from error
            if idx < 1 or idx > len(submodules):
                raise click.UsageError(f"Index {idx} out of range (1-{len(submodules)})")
            selected.append(submodules[idx - 1])
    else:
        name_map = {sub.name: sub for sub in submodules}
        not_found = [n for n in names if n not in name_map]
        if not_found:
            raise click.UsageError(f"Submodule(s) not found: {', '.join(not_found)}")
        selected = [name_map[n] for n in names]

    if not selected:
        raise click.Abort()

    # Collect all symlinks in the repo once
    all_symlinks: list[Path] = []
    for root, dirs, files in os.walk(repo_path):
        if ".git" in dirs:
            dirs.remove(".git")
        for entry in dirs + files:
            p = Path(root) / entry
            if p.is_symlink():
                all_symlinks.append(p)

    # Build removal plan: submodule → list of symlinks pointing into it
    plan = []
    for sub in selected:
        sub_rel = os.path.relpath(repo_path / sub.path, repo_path)
        links = [lnk for lnk in all_symlinks if sub_rel in os.readlink(lnk)]
        plan.append((sub, links))

    # Show summary
    click.echo("\nPlanned removals:")
    for sub, links in plan:
        click.echo(f"  [submodule] {sub.name}  ({sub.path})")
        for lnk in links:
            click.echo(f"  [symlink]   {os.path.relpath(lnk, repo_path)}")

    if dry_run:
        print_warning("Dry run — no changes applied.")
        return

    if not force:
        click.confirm("\nProceed with removal?", abort=True)

    removed_subs = []

    for sub, links in plan:
        # Remove associated symlinks from disk and index
        for lnk in links:
            rel = os.path.relpath(lnk, repo_path)
            click.echo(f"[unlink] {rel}")
            repo.git.rm("--force", "--", rel)

        # Remove submodule (cleans .gitmodules, index entry, and working dir)
        click.echo(f"[remove] {sub.name}")
        sub.remove(force=True)
        removed_subs.append(sub.name)

    if not removed_subs:
        print_warning("Nothing was removed.")
        return

    if not no_commit:
        description = "\n".join(f"- {n}" for n in removed_subs)
        commit(
            repo,
            repo_path,
            [],
            "submodules_remove",
            description=description,
            skip_hooks=True,
        )
        print_success(f"Removed {len(removed_subs)} submodule(s) and committed.")
    else:
        print_success(f"Removed {len(removed_subs)} submodule(s).")
        print_warning("Don't forget to commit: git commit -m 'chore(submodules): remove submodule(s)'")
