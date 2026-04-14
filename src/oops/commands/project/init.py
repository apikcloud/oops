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
from oops.io.file import build_compose, parse_odoo_version, volume_prefix
from oops.io.templates import ODOO_CONF
from oops.io.tools import run
from oops.services.git import get_local_repo
from oops.utils.render import print_success


@command("init", help=__doc__)
@click.option("--with-maildev", is_flag=True, default=False, help="Enable maildev service.")
@click.option("--with-sftp", is_flag=True, default=False, help="Enable SFTP service.")
@click.option("--no-dev", is_flag=True, default=False, help="Disable --dev=all flag.")
@click.option("--port", default=8069, show_default=True, help="Host port mapped to Odoo.")
@click.option("--without-workspace", is_flag=True, default=False, help="Don't generate a VSCode workspace file.")
@click.pass_context
def main(
    ctx: click.Context,
    with_maildev: bool,
    with_sftp: bool,
    no_dev: bool,
    port: int,
    without_workspace: bool,
) -> None:
    _, repo_path = get_local_repo()

    try:
        image_info = parse_odoo_version(repo_path)
    except (ValueError, FileNotFoundError) as error:
        raise click.ClickException(
            f"Could not determine Odoo image: {error or 'version file missing or empty'}"
        ) from error

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
        click.confirm(f"Overwrite {names}?", abort=True)

    config_dir.mkdir(exist_ok=True)
    compose_path.write_text(compose_content)
    conf_path.write_text(ODOO_CONF)
    run(["sudo", "chmod", "777", str(config_dir), "-R"])

    print_success("docker-compose.yml")
    print_success(".config/odoo.conf")

    if not without_workspace:
        from oops.commands.misc.create_workspace import main as create_workspace

        ctx.invoke(create_workspace)
