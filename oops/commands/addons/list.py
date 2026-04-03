# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: list.py — oops/commands/addons/list.py

"""List all addons discovered across submodules with their metadata.

Displays a table with addon name, symlink flag, submodule, upstream branch,
PR flag, version, and author. Output can be formatted as text, JSON, or CSV.
"""

import csv
import io
import json

import click

from oops.commands.base import command
from oops.utils.git import get_local_repo, is_pull_request
from oops.utils.io import find_addons
from oops.utils.net import encode_url
from oops.utils.render import human_readable, render_boolean, render_table


@command(name="list", help=__doc__)
@click.option(
    "--format",
    type=click.Choice(["text", "json", "csv"]),
    default="text",
    show_default=True,
    help="Output format",
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
    help="Show only addons that are symlinked at the repo root",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="List all addons, including those not in submodules (i.e. in the root of the repo)",
)
def main(format: str, init: bool, submodules: tuple, symlinks_only: bool, show_all: bool):

    repo, repo_path = get_local_repo()

    if init:
        for sub in repo.submodules:
            if not (repo_path / sub.path).exists():
                click.echo(f"Initialising submodule: {sub.name}")
                sub.update(init=True, recursive=False)

    # Build submodule lookup: rel_path → metadata
    subs = {}
    for sub in repo.submodules:
        try:
            canonical_url = encode_url(sub.url, "https", suffix=False)
        except (ValueError, AttributeError):
            canonical_url = ""
        try:
            branch = sub.branch_name
        except Exception:
            branch = ""
        subs[sub.path] = {
            "name": sub.name,
            "branch": branch,
            "url": canonical_url,
            "pr": is_pull_request(sub),
        }

    # Filter submodule names if requested
    active_paths = (
        {path for path, info in subs.items() if info["name"] in submodules}
        if submodules
        else None
    )

    rows = []
    seen: set = set()
    for addon in find_addons(repo_path, shallow=not show_all):
        if addon.path in seen:
            continue
        seen.add(addon.path)

        if active_paths is not None and addon.rel_path not in active_paths:
            continue

        if symlinks_only and not addon.symlink:
            continue

        sub = subs.get(addon.rel_path, {})
        rows.append(
            {
                "addon": addon.technical_name,
                "symlink": addon.symlink,
                "submodule": sub.get("name", ""),
                "upstream": sub.get("branch", ""),
                "pr": sub.get("pr", False),
                "version": addon.version,
                "author": addon.author,
            }
        )

    rows.sort(key=lambda r: r["addon"])

    if format == "json":
        click.echo(json.dumps(rows, indent=2, default=str))
    elif format == "csv":
        if rows:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
            click.echo(buf.getvalue(), nl=False)
    else:
        table_rows = [
            [
                r["addon"],
                render_boolean(r["symlink"]),
                human_readable(r["submodule"], width=30),
                human_readable(r["upstream"]),
                render_boolean(r["pr"]),
                r["version"],
                human_readable(r["author"], width=30),
            ]
            for r in rows
        ]
        click.echo(
            render_table(
                table_rows,
                headers=["Addon", "S", "Submodule", "Upstream", "PR", "Version", "Author"],
                index=True,
            )
        )
