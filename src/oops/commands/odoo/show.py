# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — oops/commands/odoo/show.py

"""
List locally available Odoo source checkouts.

Scans the sources directory for version folders and shows, for each version,
the current commit hash and author date for Community, Enterprise, and
design-themes.

The sources directory is configured via odoo.sources_dir in ~/.oops.yaml.
"""

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.compat import Optional
from oops.core.exceptions import OopsError
from oops.core.metadata import get_metadata
from oops.core.models import Result, Stat, StatGroup
from oops.io.file import require_odoo_sources
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.output.sinks import deliver
from oops.utils.git import repo_info

from .presenters.show import prepare

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="show", help=__doc__)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format. 'json' is suited for downstream consumption.",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout.",
)
def main(output_format: str, output_path: "Optional[Path]") -> None:
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()
    assert metadata is not None

    availables = require_odoo_sources()

    outer: Result[None] = Result()
    result: Result[list[dict]] = Result()
    result.data = []

    result.data = [
        {
            "version": version.version,
            "community": repo_info(version.path / "community") or "—",
            "enterprise": repo_info(version.path / "enterprise") or "—",
            "themes": repo_info(version.path / "themes") or "—",
        }
        for version in availables
    ]

    counters = StatGroup(
        name="counters",
        label="counters",
        values=[
            Stat(
                name="version",
                label="Version",
                value=len(result.data),
            ),
            Stat(
                name="community",
                label="community",
                value=sum(item.community for item in availables),
            ),
            Stat(
                name="enterprise",
                label="enterprise",
                value=sum(item.enterprise for item in availables),
            ),
            Stat(
                name="themes",
                label="themes",
                value=sum(item.themes for item in availables),
            ),
        ],
    )

    output = prepare(result, outer, target=formatter.target, metadata=metadata, stats=counters)
    deliver(formatter, output, output_format, output_path)

    if outer.errors:
        raise OopsError("; ".join(outer.errors))
