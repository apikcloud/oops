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
from oops.core.metadata import get_metadata
from oops.core.models import AddonInfo, Result
from oops.io.file import enrich_addon, find_addons
from oops.output.formatters import (
    CsvFormatter,
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SpaReportFormatter,
    SummaryConsoleFormatter,
)
from oops.output.sinks import deliver
from oops.services.git import list_submodules, require_repository
from oops.services.loc import get_addon_loc

from .presenters.list import ListPresenter

FORMATTERS: FormatterRegistry = {
    "text": SummaryConsoleFormatter,
    "json": JsonFormatter,
    "html": SpaReportFormatter,
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
def main(
    output_format: str,
    init: bool,
    submodules: tuple,
    symlinks_only: bool,
    show_all: bool,
    output_path: Path,
):

    metadata = get_metadata()

    repo, repo_path = require_repository()

    formatter: OutputFormatter = FORMATTERS[output_format]()
    result: Result[list[AddonInfo]] = Result()
    result.data = []

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

            # add lines of code
            addon.loc = get_addon_loc(addon.path)

            result.data.append(addon)

        log.info("Finalizing...")
        result.data.sort(key=lambda item: item.technical_name)

        total_loc = sum(addon.loc.total for addon in result.data if addon.loc)

        if total_loc:
            for addon in result.data:
                addon.loc_pct = round(100.0 * addon.loc.total / total_loc, 1) if addon.loc else 0.0

    # 2. Presenter prepares neutral dicts according to the formatter's audience.
    output = ListPresenter().prepare(result, target=formatter.target, metadata=metadata)
    deliver(formatter, output, output_format, output_path)
