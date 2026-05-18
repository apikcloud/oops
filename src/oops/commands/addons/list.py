# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: list.py — oops/commands/addons/list.py

"""List all addons discovered across submodules with their metadata.

Displays a table with addon name, symlink flag, submodule, upstream branch,
PR flag, version, and author. Output can be formatted as text, JSON, or CSV.
"""

import csv
import io
import json
from collections import Counter

import click
from oops.commands.base import command
from oops.core.models import AddonInfo
from oops.io.file import enrich_addon, find_addons
from oops.services.git import list_submodules, require_repository
from oops.services.loc import get_addon_loc
from oops.utils.render import (
    colorize,
    get_console,
    get_error_console,
    human_readable,
    make_table,
    metrics_grid,
    metrics_panel,
    render_boolean,
    rule,
)
from rich.live import Live
from rich.spinner import Spinner

console = get_console()


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

    repo, repo_path = require_repository()

    # using Live for long-time processing
    with Live(Spinner("dots", text="Initialisation..."), refresh_per_second=10, console=get_error_console()) as live:
        if init:
            for sub in repo.submodules:
                if not (repo_path / sub.path).exists():
                    live.update(Spinner("dots", text=f"Initialising submodule: {sub.name}"))
                    sub.update(init=True, recursive=False)

        # Build submodule lookup: rel_path → metadata
        subs = list_submodules(repo)

        # Filter submodule names if requested
        active_paths = {path for path, info in subs.items() if info["name"] in submodules} if submodules else None

        # Deduplicate by resolved path, preferring root-level symlinks over real files.
        # os.walk visits both when --all is used, and dotfile dirs (.third-party) sort
        # first, so without this the real file wins and symlinks are miscounted.
        seen: dict[str, AddonInfo] = {}
        for addon in find_addons(repo_path, shallow=not show_all):
            if addon.path not in seen or addon.symlinked:
                seen[addon.path] = addon

        rows = []
        for addon in seen.values():
            if active_paths is not None and addon.rel_path not in active_paths:
                continue

            if symlinks_only and not addon.symlink:
                continue

            live.update(Spinner("dots", text=f"Enrichment of {addon.technical_name}"))

            sub = subs.get(addon.rel_path, {})
            enrich_addon(addon, sub)

            loc = get_addon_loc(addon.path)
            rows.append(
                {
                    "addon": addon.technical_name,
                    "location": addon.location,
                    "symlink": addon.symlink,
                    "submodule": addon.submodule or "",
                    "upstream": addon.branch or "",
                    "pr": addon.pull_request or False,
                    "version": addon.version,
                    "classification": addon.classification,
                    "author": addon.author,
                    "loc_python": loc.python,
                    "loc_xml": loc.xml,
                    "loc_js": loc.javascript,
                    "loc_docs": loc.docs,
                    "loc_total": loc.total,
                    "loc_pct": 0.0,
                }
            )

        live.update(Spinner("dots", text="Finalizing..."))
        rows.sort(key=lambda r: r["addon"])

        total_loc = sum(r["loc_total"] for r in rows)
        if total_loc:
            for r in rows:
                r["loc_pct"] = round(100.0 * r["loc_total"] / total_loc, 1)

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
        total = len(rows)
        locations = Counter(row["location"] for row in rows)
        classifications = Counter(row["classification"] for row in rows)

        p1 = metrics_panel(
            "Summary",
            [
                ["Total", str(total)],
                ["Local", str(locations["local"])],
                ["Active", str(locations["active"])],
                ["Inactive", str(locations["inactive"])],
            ],
        )

        p2 = metrics_panel(
            "Classification",
            [
                ["Custom", str(classifications["custom"])],
                ["OCA", str(classifications["oca"])],
                ["Third-party", str(classifications["third-party"])],
            ],
        )

        loc_sum_py = sum(r["loc_python"] for r in rows)
        loc_sum_xml = sum(r["loc_xml"] for r in rows)
        loc_sum_js = sum(r["loc_js"] for r in rows)
        loc_sum_docs = sum(r["loc_docs"] for r in rows)

        p3 = metrics_panel(
            "Lines of code",
            [
                ["Python", str(loc_sum_py)],
                ["XML", str(loc_sum_xml)],
                ["JavaScript", str(loc_sum_js)],
                ["Docs", str(loc_sum_docs)],
                ["Total", str(total_loc)],
            ],
        )

        console.print()
        console.print(metrics_grid(p1, p2, p3))
        console.print()

        # rule("Summary")

        # kv_panel("Summary", {"Total": total, "Real": real_addons, "Symlinks": f"[green]●{symlinks}[/]"})

        columns = [
            ("Addon", "brand.primary", "left"),
            ("Symlink", "green", "center"),
            ("Submodule", "dim", "left"),
            ("Branch", "dim", "center"),
            ("PR", "green", "center"),
            ("Version", "brand.primary", "left"),
            ("Classification", "dim", ""),
            ("Author", "dim", ""),
            ("Py", "dim", "right"),
            ("XML", "dim", "right"),
            ("JS", "dim", "right"),
            ("Docs", "dim", "right"),
            ("LOC", "brand.primary", "right"),
        ]

        t = make_table(
            title=None,
            columns=columns,
            rows=[
                [
                    row["addon"],
                    colorize(render_boolean(row["symlink"]), "green"),
                    human_readable(row["submodule"]),
                    human_readable(row["upstream"]),
                    colorize(render_boolean(row["pr"]), "green"),
                    row["version"],
                    human_readable(row["classification"]),
                    human_readable(row["author"]),
                    str(row["loc_python"]) if row["loc_python"] else "",
                    str(row["loc_xml"]) if row["loc_xml"] else "",
                    str(row["loc_js"]) if row["loc_js"] else "",
                    str(row["loc_docs"]) if row["loc_docs"] else "",
                    str(row["loc_total"]) if row["loc_total"] else "",
                ]
                for row in rows
            ],
        )
        console.print(t)
        console.print()

        rule("Results")
