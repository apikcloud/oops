#!/usr/bin/env python3


import click


@click.command(name="fix")
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
def main(no_commit: bool):  # noqa: C901, PLR0912
    """Fix submodules"""

    # 1. Prune unused submodules
    # 2. Rename submodules
    # 3. Rewrite submodules

    # repo.git.submodule("set-url", submodule.path, new_url)
