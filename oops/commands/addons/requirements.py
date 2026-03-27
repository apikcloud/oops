# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from __future__ import annotations

import os
from pathlib import Path

import click

from .tools import file_updater, get_content_from_manifest


@click.command("requirements")
@click.option("--update", is_flag=True, help="Update the requirements.txt file.")
def main(update: bool = False):
    """Extract "external_dependencies" from all active modules in the root of the repository."""

    dependencies = "external_dependencies"
    requirements_txt_path = "requirements.txt"

    python_dependencies = ["# Requirements generated from manifests external_dependencies:"]
    modules = get_content_from_manifest(dependencies)
    for module in modules:
        if ext_deps := (modules[module].get(dependencies, {}).get("python", [])):
            python_dependencies.extend(ext_deps)

    python_dependencies.sort()
    python_dependencies = "\n".join(python_dependencies)

    if not os.path.exists(requirements_txt_path):
        click.secho(f"Error: {requirements_txt_path} does not exist.", fg="red")
        exit(1)

    path = Path(requirements_txt_path)
    content = path.read_text()
    if not update and content != python_dependencies:
        click.secho(
            f"Consider running `oops-addons-requirements --update`."
            f"{requirements_txt_path} is not up to date.",
            fg="yellow",
            bold=True,
        )

    if update:
        file_updater(
            filepath=requirements_txt_path,
            new_inner_content=python_dependencies,
        )
