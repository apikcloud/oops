# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: list.py — oops/commands/addons/list.py

"""List all addons discovered across submodules with their metadata.

Displays a table with addon name, symlink flag, submodule, upstream branch,
PR flag, version, and author. Output can be formatted as text, JSON, or CSV.
"""

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.logger import live_progress, log
from oops.core.models import AddonInfo, Result
from oops.io.file import enrich_addon, find_addons
from oops.output.formatters import (
    AddonsReportFormatter,
    CsvFormatter,
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SummaryConsoleFormatter,
)
from oops.output.sinks import deliver
from oops.services.git import list_submodules, require_repository
from oops.services.loc import get_addon_loc

from .presenters.list import prepare

FORMATTERS: FormatterRegistry = {
    "text": SummaryConsoleFormatter,
    "json": JsonFormatter,
    "html": AddonsReportFormatter,
    "csv": CsvFormatter,
}


@command(name="list", help=__doc__)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "csv", "html"]),
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
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
def main(output_format: str, init: bool, submodules: tuple, symlinks_only: bool, show_all: bool, output_path: Path):

    repo, repo_path = require_repository()

    formatter: OutputFormatter = FORMATTERS[output_format]()

    rows: Result[list] = Result()
    rows.data = []
    outer: Result[None] = Result()

    # 1. Long-running processing — produces a typed Result of domain dataclasses.
    with live_progress("Initialisation..."):
        if init:
            for sub in repo.submodules:
                if not (repo_path / sub.path).exists():
                    log.info(f"Initialising submodule: {sub.name}")
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

        for addon in seen.values():
            if active_paths is not None and addon.rel_path not in active_paths:
                continue

            if symlinks_only and not addon.symlink:
                continue

            log.info(f"Enrichment of {addon.technical_name}")

            sub = subs.get(addon.rel_path, {})
            enrich_addon(addon, sub)

            loc = get_addon_loc(addon.path)
            rows.data.append(
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

        log.info("Finalizing...")
        rows.data.sort(key=lambda r: r["addon"])

        total_loc = sum(r["loc_total"] for r in rows.data)
        if total_loc:
            for r in rows.data:
                r["loc_pct"] = round(100.0 * r["loc_total"] / total_loc, 1)

    # 2. Presenter prepares neutral dicts according to the formatter's audience.
    output = prepare(rows, outer, target=formatter.target)
    deliver(formatter, output, output_format, output_path)
