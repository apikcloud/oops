# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: update.py — oops/commands/requirements/update.py

"""
Update the requirements file of the project depending on the python dependencies found in the project.
It checks the python dependencies in each manifest of the root addons.

The whole content of the requirements file is replaced by the python dependencies found in the project.

By default, a commit is automatically done to push the changes. Use --no-commit to avoid this behaviour.

"""

from __future__ import annotations

from pathlib import Path

import click
from git import Repo

from oops.core.config import config
from oops.core.messages import commit_messages
from oops.utils.io import file_updater, get_python_dependencies


@click.command("update")
@click.option("--no-commit", is_flag=True, help="Do not commit changes.")
def main(no_commit: bool):
    requirement_file = Path(config.project_file_requirements)
    repo = Repo()
    repo_path = Path(repo.working_dir)

    has_changes, python_dependencies, diff = get_python_dependencies(requirement_file, repo_path)

    python_dependencies_str = "\n".join(python_dependencies)

    if not has_changes:
        click.echo("No changes detected in requirements.")
        return

    click.echo(f"Updating {requirement_file}...")
    has_update = file_updater(
        filepath=str(requirement_file),
        new_inner_content=python_dependencies_str,
    )

    if has_update and not no_commit:
        click.echo("Committing changes...")
        repo.index.add([str(requirement_file)])
        repo.index.commit(commit_messages.requirements_updated, skip_hooks=True)
    else:
        click.secho("\nNo files were modified.", fg="yellow")
