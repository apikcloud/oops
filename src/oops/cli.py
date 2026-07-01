# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: cli.py — oops/cli.py

import importlib
import pkgutil

import click
import oops.commands as _commands_pkg
from oops.commands.dashboard import main as dashboard
from oops.commands.mcp import main as mcp

# Modules inside a group package that are helpers, not commands.
_SKIP = {"common"}


@click.group()
@click.version_option(package_name="oops")
def main():
    pass


for _group_info in pkgutil.iter_modules(_commands_pkg.__path__):
    if not _group_info.ispkg:
        continue  # skip base.py

    _group_pkg = importlib.import_module(f"oops.commands.{_group_info.name}")

    # If the package defines its own group command, use it (enables group-level options).
    if hasattr(_group_pkg, "main") and isinstance(getattr(_group_pkg, "main"), click.Group):
        _grp = _group_pkg.main
        _grp.name = _group_info.name
    else:
        _grp = click.Group(name=_group_info.name, help=_group_pkg.__doc__)

    for _cmd_info in pkgutil.iter_modules(_group_pkg.__path__):
        if _cmd_info.name in _SKIP or _cmd_info.name.startswith("_") or _cmd_info.ispkg:
            continue
        _mod = importlib.import_module(f"oops.commands.{_group_info.name}.{_cmd_info.name}")
        if hasattr(_mod, "main"):
            _grp.add_command(_mod.main)

    if _grp.commands:
        main.add_command(_grp)


main.add_command(dashboard)
main.add_command(mcp)
