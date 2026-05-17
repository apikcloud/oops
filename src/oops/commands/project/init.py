# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: init.py — src/oops/commands/project/init.py

"""
Bootstrap a new Odoo project in the current repository.

Reads the Docker image reference from odoo_version.txt, then writes:

  - docker-compose.yml  — Compose stack (Odoo + Postgres, optional maildev/SFTP)
  - .config/odoo.conf   — Odoo server configuration file
  - <repo>.code-workspace — VSCode workspace with Odoo analysis paths (skipped with --without-workspace)

Prompts before overwriting any existing file.
"""

from __future__ import annotations

import click
from oops.commands.base import command
from oops.core.exceptions import AppAbort
from oops.io.file import build_compose, volume_prefix
from oops.io.templates import ODOO_CONF
from oops.io.tools import run
from oops.services.git import require_repository
from oops.services.project import require_project
from oops.utils.render import conclude, print_success, prompt_confirm, rule


@command("init", help=__doc__)
@click.option("--with-maildev", is_flag=True, default=False, help="Enable maildev service.")
@click.option("--with-sftp", is_flag=True, default=False, help="Enable SFTP service.")
@click.option("--no-dev", is_flag=True, default=False, help="Disable --dev=all flag.")
@click.option("--port", default=8069, show_default=True, help="Host port mapped to Odoo.")
@click.option("--without-workspace", is_flag=True, default=False, help="Don't generate a VSCode workspace file.")
@click.option(
    "--include-sources", is_flag=True, default=False, help="Include the Odoo sources as folders in the workspace."
)
@click.pass_context
def main(
    ctx: click.Context,
    with_maildev: bool,
    with_sftp: bool,
    no_dev: bool,
    port: int,
    without_workspace: bool,
    include_sources: bool,
) -> None:
    _, repo_path = require_repository()

    image_info = require_project(repo_path)

    rule(f"Initialize Odoo {image_info.major_version} project — {repo_path.name}")

    compose_content = build_compose(
        odoo_version=image_info.major_version,
        image=image_info.image,
        port=port,
        prefix=volume_prefix(repo_path),
        dev=not no_dev,
        with_maildev=with_maildev,
        with_sftp=with_sftp,
    )

    compose_path = repo_path / "docker-compose.yml"
    config_dir = repo_path / ".config"
    conf_path = config_dir / "odoo.conf"

    existing = [p for p in (compose_path, conf_path) if p.exists()]
    if existing:
        names = ", ".join(str(p.relative_to(repo_path)) for p in existing)
        if not prompt_confirm(f"Overwrite {names}?", default=False):
            raise AppAbort()

    config_dir.mkdir(exist_ok=True)
    compose_path.write_text(compose_content)
    conf_path.write_text(ODOO_CONF)
    run(["sudo", "chmod", "777", str(config_dir), "-R"])

    print_success("docker-compose.yml")
    print_success(".config/odoo.conf")

    if not without_workspace:
        from oops.commands.misc.create_workspace import main as create_workspace

        ctx.invoke(create_workspace, include_sources=include_sources)

    conclude(True, "Project initialised")
