# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — oops/commands/manifest/check.py

"""
[EXPERIMENTAL] Check all Odoo manifest files against the oops lint rules.

Scans the repository for __manifest__.py files and runs the rules defined
in oops.rules.manifest (author/maintainers, key order). Reports violations
and exits non-zero if any are found.

Accepts either addon names (CLI) or file paths (pre-commit hook). When run
without arguments, all owned installable addons are checked.

Use oops-man-fix to apply autofixes.
"""

from pathlib import Path

import click
from oops.commands.base import command
from oops.commands.manifest.common import collect_paths, run_fixit
from oops.io.file import get_filtered_addon_names
from oops.io.manifest import get_manifest_path
from oops.services.git import get_local_repo


@command(name="check", help=__doc__)
@click.argument("inputs", nargs=-1)
@click.option("--diff", is_flag=True, help="Show the autofix diff alongside each violation.")
def main(inputs: tuple, diff: bool) -> None:
    _, repo_path = get_local_repo()

    if not inputs:
        names = get_filtered_addon_names(repo_path)
        paths = collect_paths(repo_path, names)
    else:
        paths: list[Path] = []
        names = []
        for inp in inputs:
            p = Path(inp)
            if p.is_file():
                # Pre-commit passes manifest file paths directly.
                paths.append(p)
            elif p.is_dir():
                # Addon directory passed explicitly — resolve its manifest.
                manifest = get_manifest_path(str(p))
                if manifest:
                    paths.append(Path(manifest))
            else:
                # Plain addon name — resolve via repo scan.
                names.append(inp)
        if names:
            paths.extend(collect_paths(repo_path, names))

    if not paths:
        click.echo("No manifest files found.")
        raise click.exceptions.Exit(0)

    violations = run_fixit(paths, autofix=False, show_diff=diff)

    if violations:
        raise click.exceptions.Exit(1)

    click.echo(f"All {len(paths)} manifest(s) passed.")
