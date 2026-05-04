# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — oops/commands/requirements/update.py

"""
Update the requirements file of the project depending on the python dependencies found in the project.
It checks the python dependencies in each manifest of the root addons.

The whole content of the requirements file is replaced by the python dependencies found in the project.

By default, a commit is automatically done to push the changes. Use --no-commit to avoid this behaviour.

Merging rules
-------------
When multiple addons declare constraints for the same package, they are merged
before comparison:

 1. Bare name (no operator)   — kept as-is, deduplicated across addons.
 2. Single floor (>= / >)     — kept as-is.
 3. Single ceil  (<= / <)     — kept as-is.
 4. Multiple floors           — highest version wins (most restrictive).
 5. Multiple ceils            — lowest version wins (most restrictive).
 6. Floor + ceil              — merged as ``pkg>=floor,<ceil``.
 7. > vs >= at same version   — strict operator wins (> beats >=, < beats <=).
 8. == pin                    — always kept as-is; if a range also exists for the same package, both are emitted
 (human arbitration).
 9. Git dep (e.g. pkg@git+…)  — no <=> in string → treated as bare name, passes through unchanged, no merging.
10. Name mapping              — import names are normalized to pip names before any version processing (PIL → Pillow,
 dateutil → python-dateutil, and so on...).
11. Final output              — alphabetically sorted; header line prepended.
"""

from __future__ import annotations

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.io.file import file_updater, get_requirements_diff
from oops.services.git import commit, get_local_repo


@command("update", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes.")
def main(dry_run: bool, no_commit: bool):
    repo, repo_path = get_local_repo()
    requirement_file = Path(config.project.file_requirements)

    has_changes, python_dependencies, _ = get_requirements_diff(repo_path)
    python_dependencies_str = "\n".join(python_dependencies)

    if not has_changes:
        click.echo("No changes detected in requirements.")
        raise click.exceptions.Exit(0)

    has_update = file_updater(
        filepath=str(requirement_file),
        new_inner_content=python_dependencies_str,
        dry_run=dry_run,
    )

    if has_update and not no_commit and not dry_run:
        commit(repo, repo_path, [requirement_file], "requirements_updated", skip_hooks=True)
