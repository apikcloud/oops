#!/usr/bin/env python3

import click

from osh.gitutils import git_top, parse_submodules
from osh.io import symlink_targets


@click.command(name="check")
def main():  # noqa: C901
    """Check that all submodules are under .third-party and used by at least one symlink."""

    repo = git_top()
    gm = repo / ".gitmodules"
    if not gm.exists():
        click.echo("No .gitmodules found.")
        return 0

    subs = parse_submodules(gm)

    if not subs:
        click.echo("No submodules found.")
        return 0

    targets = symlink_targets(repo)
    bad_paths = []
    unused = []

    for name, item in subs.items():
        path = item["path"]
        if not path.startswith(".third-party/"):
            bad_paths.append((name, path))
        # Check if any symlink target mentions this path
        if not any(path in t for t in targets):
            unused.append((name, path))

    ok = True
    if bad_paths:
        click.echo(f"❌ Submodules not under .third-party ({len(bad_paths)}):")
        for name, path in bad_paths:
            click.echo(f"  - {name}: {path}")
        ok = False

    if unused:
        click.echo("❌ Unused submodules (no symlink points to them):")
        for name, path in unused:
            click.echo(f"  - {name}: {path}")
        ok = False

    if ok:
        click.echo("✅ All submodules are under .third-party and used by at least one symlink.")
        return 0
    else:
        return 1
