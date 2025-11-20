#!/usr/bin/env python3

import click

from oops.git.core import GitRepository
from oops.utils.io import symlink_targets


@click.command(name="check")
def main():  # noqa: C901
    """Check that all submodules are under .third-party and used by at least one symlink."""

    repo = GitRepository()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.")
        return 0

    # FIXME: parse_gitmodules is a generator now
    # not subs anymore
    # if not subs:
    #     click.echo("No submodules found.")
    #     return 0

    targets = symlink_targets(repo.path)
    bad_paths = []
    unused = []

    for submodule in repo.parse_gitmodules():
        if not submodule.path.startswith(".third-party/"):
            bad_paths.append((submodule.name, submodule.path))
        # Check if any symlink target mentions this path
        if not any(submodule.path in t for t in targets):
            unused.append((submodule.name, submodule.path))

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
