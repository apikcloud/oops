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
from oops.commands.base import command, render_and_exit
from oops.core.compat import Optional
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.io.file import require_odoo_sources
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.utils.git import repo_info

from .presenters.show import ShowPresenter

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

    availables = require_odoo_sources()

    result: Result[dict] = Result(
        {
            "rows": [
                {
                    "version": version.version,
                    "community": repo_info(version.path / "community") or "—",
                    "enterprise": repo_info(version.path / "enterprise") or "—",
                    "themes": repo_info(version.path / "themes") or "—",
                }
                for version in availables
            ],
            "metrics": {},
        }
    )

    assert result.data

    result.data["metrics"] = {
        "versions": len(result.data["rows"]),
        "community": sum(item.community for item in availables),
        "enterprise": sum(item.enterprise for item in availables),
        "themes": sum(item.themes for item in availables),
    }

    output = ShowPresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)
