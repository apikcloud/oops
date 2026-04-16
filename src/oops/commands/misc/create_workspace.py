# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: create_workspace.py — oops/commands/misc/create_workspace.py

"""
Generate a VSCode workspace file for the current Odoo project.

Reads the Odoo version from odoo_version.txt at the repository root,
falling back to manifest.odoo_version in config, then writes a
<repo-name>.code-workspace file at the repository root configured with
Python analysis paths pointing to the local Odoo sources.

The sources directory is read from odoo.sources_dir in ~/.oops.yaml.
"""

import json
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.io.file import get_odoo_sources_dirs, parse_odoo_version
from oops.services.git import get_local_repo
from oops.utils.compat import Optional
from oops.utils.render import print_success, print_warning


@command(name="create-workspace", help=__doc__)
@click.option(
    "--output",
    default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="Workspace file path. Defaults to <repo-name>.code-workspace at repo root.",
)
@click.option("--without-download", is_flag=True, default=False, help="Don't download Odoo sources if missing.")
@click.option(
    "--include-sources", is_flag=True, default=False, help="Include the Odoo sources as folders in the workspace."
)
@click.pass_context
def main(ctx: click.Context, output: Optional[str], without_download: bool, include_sources: bool) -> None:
    _, repo_path = get_local_repo()

    try:
        image_info = parse_odoo_version(repo_path)
        version = str(image_info.major_version)
        enterprise = image_info.enterprise
    except ValueError as e:
        version = config.manifest.odoo_version
        enterprise = config.manifest.edition == "enterprise"  # type: ignore[attr-defined]
        if not version:
            raise click.ClickException(
                f"Could not read Odoo version from {config.project.file_odoo_version}"
                " and manifest.odoo_version is not set."
            ) from e
        print_warning(f"Could not read version from {config.project.file_odoo_version}, using {version}.")

    workspace_file = Path(output) if output else repo_path / f"{repo_path.name}.code-workspace"

    community_dir, enterprise_dir = get_odoo_sources_dirs(version)

    if not community_dir.exists() or (not enterprise_dir.exists() and enterprise):
        if not without_download:
            from oops.commands.odoo.download import main as download

            ctx.invoke(download, version=version, do_update=True, with_enterprise=enterprise)
        else:
            print_warning("Odoo sources missing, please check before using the workspace.")

    paths = [str(community_dir)]
    if enterprise:
        paths.append(str(enterprise_dir))
    folders = [{"path": "."}]
    if include_sources:
        folders += [{"path": path} for path in paths]
    workspace = {
        "folders": folders,
        "settings": {
            "python.analysis.extraPaths": paths,
            "python.autoComplete.extraPaths": paths,
        },
    }

    workspace_file.write_text(json.dumps(workspace, indent=4) + "\n")
    print_success(f"Workspace written to '{workspace_file}' (Odoo {version}).")
