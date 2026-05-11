# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — oops/commands/requirements/check.py

"""
Check the differences between the existing requirements and the expected ones.

The expected requirements are computed by scanning every root addon manifest and
collecting their ``external_dependencies["python"]`` entries.

In case of changes, it will be displayed like this:

    Changes for requirements.txt:

    - astor
    + pandas
    + python-stdnum
    - pytz
    + pytz==2023.3

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
from oops.io.file import get_requirements_diff
from oops.services.git import get_local_repo
from oops.utils.render import print_error, print_success


@command("check", help=__doc__)
@click.option("--no-fail", is_flag=True, default=False, help="Exit 0 even when changes are detected.")
def main(no_fail):
    _, repo_path = get_local_repo()
    requirement_file = Path(config.project.file_requirements)

    has_changes, _, diff = get_requirements_diff(repo_path)

    if not has_changes:
        print_success("No changes detected in requirements.")
        raise click.exceptions.Exit(0)

    click.echo(f"Changes for {requirement_file}:")
    for line in diff:
        if line.startswith("- "):
            print_error(line, symbol="")
        elif line.startswith("+ "):
            print_success(line, symbol="")

    raise click.exceptions.Exit(0 if no_fail else 1)
