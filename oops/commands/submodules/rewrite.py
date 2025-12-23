#!/usr/bin/env python3

import contextlib
import os
import subprocess
from pathlib import Path

import click

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.git.core import GitRepository
from oops.git.gitutils import (
    git_config_submodule,
)
from oops.git.submodules import GitSubmodules
from oops.utils.io import (
    ask,
    desired_path,
    is_dir_empty,
    is_pull_request_path,
    rewrite_symlink,
    symlink_targets,
)
from oops.utils.render import human_readable


@click.command(name="rewrite")
@click.option(
    "--base-dir",
    default=config.new_submodule_path,
    help="Base directory for rewritten paths (default: .third-party)",
)
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
@click.option(
    "--old-base-dir",
    default=None,
    help="Old base dir to prune if empty (default: auto-detect, fallback 'third-party')",
)
def main(base_dir: str, force: bool, dry_run: bool, no_commit: bool, old_base_dir: str):  # noqa: C901, PLR0912, PLR0915
    """
    Rewrite submodule paths to be under a common base dir (e.g. .third-party).
    Also rewrites symlinks.
    """

    repo = GitRepository()
    submodules = GitSubmodules()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.")
        return 0

    # FIXME: assume there is only one symlink per submodule for now
    symlinks = {str(Path(t).parent): Path(t).name for t in symlink_targets(repo.path)}

    plan = []
    for submodule in repo.parse_gitmodules():
        print(submodule)
        if not submodule.url:
            click.echo(f"[warn] submodule '{submodule.name}' has no URL, skipping")
            continue

        # Ensure we have a symlink target for this submodule
        if submodule.path not in symlinks:
            click.echo(
                f"[warn] submodule '{submodule.name}' path '{submodule.path}' has no symlink, skipping"
            )
            continue

        pull_request = is_pull_request_path(submodule.path) or is_pull_request_path(submodule.name)
        first_symlink = symlinks[submodule.path] if pull_request else None
        target = desired_path(
            submodule.url, prefix=base_dir, pull_request=pull_request, suffix=first_symlink
        )

        if submodule.path != target:
            plan.append((submodule.name, submodule.url, submodule.path, target))

    if not plan:
        click.echo("No submodule needs rewriting.")
        return 0

    click.echo(f"Repo: {repo.path}")
    for name, url, oldp, newp in plan:
        click.echo(f"[plan] {name}\n  url : {url}\n  path: {oldp} -> {newp}")

    if dry_run:
        click.echo("Dry-run only.")
        return 0

    accepted = []
    for name, url, oldp, newp in plan:
        if force:
            accepted.append((name, url, oldp, newp))
        else:
            ans = ask(f"\nApply change for '{name}' ({oldp} -> {newp})? [Y/n/e] ", default="y")
            if ans in ("y", "yes"):
                accepted.append((name, url, oldp, newp))
            elif ans == "e":
                custom = input("Enter custom target path: ").strip()
                if custom:
                    accepted.append((name, url, oldp, custom))

    if not accepted:
        click.echo("Nothing accepted. Exiting.")
        return 0

    # Update .gitmodules
    for name, _, _, newp in accepted:
        git_config_submodule(str(repo.gitmodules), name, "path", newp)

    repo.add([str(repo.gitmodules)])

    # Move folders
    for _, _, oldp, newp in accepted:
        src = repo.path / oldp
        dst = repo.path / newp
        if src.exists():
            click.echo(f"[move] {oldp} -> {newp}")
            repo.move(src, dst)
        else:
            # try to init submodule if missing
            click.echo(f"[info] '{oldp}' not found; trying submodule init")

            with contextlib.suppress(subprocess.CalledProcessError):
                submodules.update(oldp)

            if (repo.path / oldp).exists():
                click.echo(f"[move] {oldp} -> {newp}")
                repo.move(repo.path / oldp, dst)
            else:
                click.echo(f"[warn] skip move: {oldp} still not found")

    # Sync and update submodule metadata
    submodules.sync()
    submodules.update()

    # Rewrite symlinks
    rewrites = 0
    # Build a quick lookup for old->new prefixes
    renames = [(oldp, newp) for (_, _, oldp, newp) in accepted]
    for root, dirs, files in os.walk(repo.path):
        if ".git" in dirs:
            dirs.remove(".git")
        for name in dirs + files:
            p = Path(root) / name
            if p.is_symlink():
                for oldp, newp in renames:
                    if rewrite_symlink(p, oldp, newp):
                        rewrites += 1
                        break
    click.echo(f"Symlinks rewritten: {rewrites}")

    # Prune old base dir if empty (auto-detect or --old-base-dir)
    old_base = old_base_dir
    if not old_base:
        # auto-detect from first path segment of old paths if unique, else fallback
        first_segments = {op.split("/", 1)[0] for (_, _, op, _) in accepted if "/" in op}
        old_base = first_segments.pop() if len(first_segments) == 1 else config.old_submodule_path

    old_base_path = repo.path / old_base
    if is_dir_empty(old_base_path):
        click.echo(f"[prune] removing empty dir: {old_base_path}")

        with contextlib.suppress(OSError):
            old_base_path.rmdir()

    # Stage everything just in case (symlinks/renames)
    repo.add_all()

    # Auto commit with detailed message
    if not no_commit:
        lines = [
            "Modified submodules:",
        ]
        lines += [f"- {name}: {oldp} -> {newp}" for (name, _, oldp, newp) in accepted]
        repo.commit(
            commit_messages.submodules_rewrite,
            description=human_readable(lines, sep="\n"),
            skip_hook=True,
        )

        click.echo("Changes committed.")
    else:
        click.echo("Changes staged but not committed (--no-commit).")
