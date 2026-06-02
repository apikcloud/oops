# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — oops/commands/project/check.py

"""
Validate project configuration and list available Odoo Docker images.

Checks for mandatory project files, verifies the configured Odoo image, and
reports warnings and errors. Exits non-zero if errors are found; with --strict,
warnings also cause a non-zero exit.
"""

from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.core.checks import CheckOutcome
from oops.core.config import config
from oops.core.metadata import get_metadata
from oops.core.models import ResultCollection
from oops.io.file import parse_odoo_version
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    PreCommitFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.output.presenters import DefaultCheckPresenter
from oops.services.docker import CheckImage, ImageCheckContext
from oops.services.git import require_repository
from oops.services.project import CheckMandatoryFiles, CheckRecommendedFiles, ProjectCheckContext

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="check", help=__doc__)
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors",
)
@click.option(
    "--hook",
    is_flag=True,
    help="Minimal output for pre-commit hooks.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
def main(strict: bool, hook: bool, output_format: str, output_path: Path):

    metadata = get_metadata()

    _, repo_path = require_repository()

    formatter: OutputFormatter = FORMATTERS[output_format]()
    if hook:
        formatter = PreCommitFormatter()

    results: ResultCollection[CheckOutcome] = ResultCollection(title="Project check")

    project_ctx: ProjectCheckContext = ProjectCheckContext(
        path=repo_path,
        enabled=["check_recommended_files", "check_mandatory_files"],
        strict=strict,
        config=config.project,
    )

    results.add(CheckMandatoryFiles(project_ctx).run())
    results.add(CheckRecommendedFiles(project_ctx).run())

    try:
        image_info = parse_odoo_version(repo_path)
        image_ctx = ImageCheckContext(
            enabled=["check_image"],
            image=image_info,
            config=config.images,
        )

        results.add(CheckImage(image_ctx).run())

    except (FileNotFoundError, ValueError) as e:
        results.add_error(str(e) or "Could not parse Odoo version.")

    output = DefaultCheckPresenter().prepare(results, target=formatter.target, metadata=metadata)
    render_and_exit(results, formatter, output, output_format, output_path)
