# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: replace.py — src/oops/commands/pr/replace.py


"""
Replace a PR based on its upstream, taking addons into account.
"""

from pathlib import Path

import click
from oops.commands.base import command


@command("replace", help=__doc__)
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    required=True,
    help="Personal Access Token GitHub (or envvar GITHUB_TOKEN).",
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
def main(token: str, output_format: str, output_path: Path):

    # TODO: Allow the user to select the PR(s) from the list of resolved PRs (those for which the upstream is known).
    # Then, list the current symlinks, remove them, and delete the relevant submodule.
    # If the target (upstream) repository does not exist locally, create it
    # using the Odoo major version as a reference. Then recreate the symlinks.

    raise NotImplementedError()
