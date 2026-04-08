# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: create_workspace.py — oops/commands/misc/create_workspace.py

"""
Generate a VSCode workspace file for the current Odoo project.

Reads the Odoo version from odoo_version.txt at the repository root,
falling back to manifest.odoo_version in config, then writes a
<repo-name>.code-workspace file at the repository root configured with
Python analysis paths pointing to the local Odoo sources.

The sources directory is read from odoo.sources_dir in ~/.oops.yaml
and can be overridden with --base-dir.
"""

import json
from pathlib import Path

import click

from oops.commands.base import command
from oops.core.config import config
from oops.io.file import parse_odoo_version
from oops.services.git import get_local_repo
from oops.utils.compat import Optional
from oops.utils.render import print_success, print_warning


@command(name="create-workspace", help=__doc__)
@click.option(
    "--base-dir",
    default=None,
    type=click.Path(file_okay=False),
    help="Root directory for Odoo sources. Defaults to odoo.sources_dir in config.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="Workspace file path. Defaults to <repo-name>.code-workspace at repo root.",
)
def main(base_dir: Optional[str], output: Optional[str]) -> None:
    _, repo_path = get_local_repo()

    sources_root = Path(base_dir) if base_dir else config.odoo.sources_dir
    if sources_root is None:
        raise click.UsageError(
            "No base directory provided. Pass --base-dir or set odoo.sources_dir in ~/.oops.yaml."
        )

    try:
        version = str(parse_odoo_version(repo_path).major_version)
    except ValueError as e:
        version = config.manifest.odoo_version
        if not version:
            raise click.ClickException(
                f"Could not read Odoo version from {config.project.file_odoo_version}"
                " and manifest.odoo_version is not set."
            ) from e
        print_warning(
            f"Could not read version from {config.project.file_odoo_version}, using {version}."
        )

    odoo_path = sources_root / version
    workspace_file = Path(output) if output else repo_path / f"{repo_path.name}.code-workspace"

    workspace = {
        "folders": [{"path": "."}],
        "settings": {
            # "[xml]": {"editor.semanticHighlighting.enabled": False},
            # "[python]": {"editor.semanticHighlighting.enabled": True},
            "python.analysis.extraPaths": [
                str(odoo_path / "community"),
                str(odoo_path / "enterprise"),
            ],
            "python.autoComplete.extraPaths": [
                str(odoo_path / "community"),
                str(odoo_path / "enterprise"),
            ],
            # "python.languageServer": "None",
        },
    }

    workspace_file.write_text(json.dumps(workspace, indent=4) + "\n")
    print_success(f"Workspace written to '{workspace_file}' (Odoo {version}).")
