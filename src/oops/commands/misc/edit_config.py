# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: edit_config.py — oops/commands/misc/edit_config.py

"""
Open an oops configuration file in the default editor.

Opens ~/.oops.yaml (global) by default, or .oops.yaml in the current
directory (local) when --local is passed. Creates the file with a starter
template if it does not exist yet.
"""

import click
from oops.commands.base import command
from oops.core.paths import CONFIG_GLOBAL, CONFIG_LOCAL
from oops.io.templates import CONFIG_STARTER
from oops.services.git import get_local_repo
from oops.utils.render import print_success


@command(name="edit-config", help=__doc__)
@click.option(
    "--local",
    "scope",
    flag_value="local",
    help="Edit the local config (.oops.yaml in the current directory)",
)
@click.option(
    "--global",
    "scope",
    flag_value="global",
    default=True,
    help="Edit the global config (~/.oops.yaml) [default]",
)
def main(scope: str) -> None:
    path = CONFIG_LOCAL if scope == "local" else CONFIG_GLOBAL

    if not path.exists():
        if scope == "local":
            _ = get_local_repo()

        print_success(f"Creating {path}")
        path.write_text(CONFIG_STARTER)

    click.edit(filename=str(path))
