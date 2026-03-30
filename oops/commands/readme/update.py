# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: update.py — oops/commands/readme/update.py

"""
This script replaces markers in the README.md file
of an repository with the list of addons present
in the repository. It preserves the marker so it
can be run again.

Markers in README.md must have the form:

\b
<!-- prettier-ignore-start -->
[//]: # (addons)
does not matter, will be replaced by the script
[//]: # (end addons)
<!-- prettier-ignore-end -->
"""

import logging
import re
from pathlib import Path

import click
from git import Repo

from oops.core.exceptions import MarkersNotFound
from oops.core.messages import commit_messages
from oops.utils.io import collect_addon_paths, load_manifest
from oops.utils.render import render_maintainers, render_markdown_table, sanitize_cell

_logger = logging.getLogger(__name__)

MARKERS = r"(\[//\]: # \(addons\))|(\[//\]: # \(end addons\))"
PARTS_NUMBER = 7


def replace_in_readme(readme_path, header, rows_available, rows_unported) -> bool:
    with open(readme_path, encoding="utf8") as f:
        original = f.read()
    parts = re.split(MARKERS, original, flags=re.MULTILINE)
    if len(parts) != PARTS_NUMBER:
        raise MarkersNotFound(f"Addons markers not found or incorrect in {readme_path}")
    addons = []
    # TODO Use the same heading styles as Prettier (prefixing the line with
    # `##` instead of adding all `----------` under it)
    if rows_available:
        addons.extend(
            [
                "\n",
                "\n",
                "Available addons\n",
                "----------------\n",
                render_markdown_table(header, rows_available),
                "\n",
            ]
        )
    if rows_unported:
        addons.extend(
            [
                "\n",
                "\n",
                "Unported addons\n",
                "---------------\n",
                render_markdown_table(header, rows_unported),
                "\n",
            ]
        )
    addons.append("\n")
    parts[2:5] = addons
    updated = "".join(parts)
    if updated == original:
        return False
    with open(readme_path, "w", encoding="utf8") as f:
        f.write(updated)
    return True


@click.command(
    help=__doc__,
    name="update",
)
@click.option(
    "--commit/--no-commit",
    default=True,
    help="git commit changes to README.rst, if any.",
)
def main(commit):  # noqa: C901
    """Generate or update the addons table in README.md."""

    repo = Repo()
    working_dir = Path(repo.working_dir)
    readme = working_dir / "README.md"

    if not readme.is_file():
        readme.write_text(
            "<!-- prettier-ignore-start -->\n"
            "[//]: # (addons)\n"
            "[//]: # (end addons)\n"
            "<!-- prettier-ignore-end -->\n",
            encoding="utf-8",
        )
        click.echo(f"Created {readme} with addon table markers.")

    header = ("addon", "version", "maintainers", "summary")
    rows_available = []
    rows_unported = []

    for addon_path, unported in collect_addon_paths(working_dir):
        manifest = load_manifest(addon_path)
        if not manifest:
            continue

        link = f"[{addon_path.name}]({addon_path}/)"
        version = manifest.get("version") or ""
        summary = sanitize_cell(manifest.get("summary") or manifest.get("name"))
        installable = manifest.get("installable", True)

        if unported and installable:
            _logger.warning(f"{addon_path} is in __unported__ but is marked installable.")
            installable = False

        row = (link, version, render_maintainers(manifest), summary)
        if installable:
            rows_available.append(row)
        else:
            rows_unported.append(
                (link, version + " (unported)", render_maintainers(manifest), summary)
            )

    changed = replace_in_readme(readme, header, rows_available, rows_unported)
    if commit and changed:
        repo.index.add(["README.md"])
        repo.index.commit(commit_messages.addons_update_table)
