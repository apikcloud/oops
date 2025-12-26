#!/usr/bin/env python3

import click

from oops.git.core import GitRepository
from oops.utils.io import find_addons
from oops.utils.net import encode_url
from oops.utils.render import human_readable, render_boolean, render_table


@click.command(name="list")
@click.option(
    "--format",
    type=click.Choice(["text", "json", "csv"]),
    default="text",
    show_default=True,
    help="Output format (default: text)",
)
@click.option(
    "--init/--no-init",
    is_flag=True,
    help="Run 'git submodule update --init' for submodules whose path is missing on disk",
)
@click.option(
    "--name",
    "-n",
    "submodules",
    multiple=True,
    help="Limit to these submodule names (as in .gitmodules)",
)
@click.option(
    "--symlinks-only",
    is_flag=True,
    help="Limit to these submodule names (as in .gitmodules)",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="List all addons, including those not in submodules (i.e. in the root of the repo)",
)
def main(format: str, init: bool, submodules: tuple, symlinks_only: bool, show_all: bool):  # noqa: C901, PLR0912
    """List all addons found in git submodules."""

    # FIXME:
    repo = GitRepository()

    rows = []
    paths = []

    # gather submodules info
    subs = {}
    if repo.has_gitmodules:
        for submodule in repo.parse_gitmodules():
            canonical_url, _, _ = (
                encode_url("https", submodule.url, suffix=False)
                if submodule.url
                else ("", None, None)
            )

            subs[submodule.path] = {
                "name": submodule.name,
                "path": submodule.path,
                "branch": submodule.branch or "",
                "url": canonical_url,
                "pr": submodule.pr,
            }

    for addon in find_addons(repo.path, shallow=not show_all):
        # FIXME: this is a bit of a hack, should be improved
        # skip duplicates (can happen if an addon is in a submodule and in the root)
        if addon.path in paths:
            continue

        paths.append(addon.path)

        sub = subs.get(addon.rel_path, {})

        rows.append(
            [
                addon.technical_name,
                render_boolean(addon.symlink),
                # human_readable(addon.rel_path, width=40),
                human_readable(sub.get("name", ""), width=30),
                human_readable(sub.get("branch", "")),
                render_boolean(sub.get("pr", False)),
                addon.version,
                human_readable(addon.author, width=30),
            ]
        )

    # sort by addon name
    rows.sort(key=lambda r: r[0])

    click.echo(
        render_table(
            rows,
            headers=["Addon", "S", "Submodule", "Upstream", "PR", "Version", "Author"],
            index=True,
        )
    )

    return 0
