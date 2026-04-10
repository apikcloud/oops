# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: view_doc.py — oops/commands/misc/view_doc.py

"""Open the oops documentation in the default browser."""

import click

from oops.commands.base import command
from oops.core.config import DOCS_URL


@command(name="view-doc", help=__doc__)
def main() -> None:
    click.launch(DOCS_URL)
