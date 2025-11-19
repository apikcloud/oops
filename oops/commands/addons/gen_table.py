#!/usr/bin/env python
# License AGPLv3 (https://www.gnu.org/licenses/agpl-3.0-standalone.html)
"""
This script replaces markers in the README.md file
of an OCA repository with the list of addons present
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

import ast
import logging
import os
import re

import click

from oops.git.gitutils import commit_if_needed

_logger = logging.getLogger(__name__)

MARKERS = r"(\[//\]: # \(addons\))|(\[//\]: # \(end addons\))"
MANIFESTS = ("__openerp__.py", "__manifest__.py")
PARTS_NUMBER = 7


def sanitize_cell(s):
    if not s:
        return ""
    s = " ".join(s.split())
    return s


def render_markdown_table(header, rows):
    table = []
    rows = [header, ["---"] * len(header)] + rows
    for row in rows:
        table.append(" | ".join(row))
    return "\n".join(table)


def render_maintainers(manifest):
    maintainers = manifest.get("maintainers") or []
    return " ".join(
        [
            f"<a href='https://github.com/{x}'>"
            f"<img src='https://github.com/{x}.png' width='32' height='32' style='border-radius:50%;' alt='{x}'/>"  # noqa: E501
            "</a>"
            for x in maintainers
        ]
    )


def replace_in_readme(readme_path, header, rows_available, rows_unported):
    with open(readme_path, encoding="utf8") as f:
        readme = f.read()
    parts = re.split(MARKERS, readme, flags=re.MULTILINE)
    if len(parts) != PARTS_NUMBER:
        _logger.warning("Addons markers not found or incorrect in %s", readme_path)
        return
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
    readme = "".join(parts)
    with open(readme_path, "w", encoding="utf8") as f:
        f.write(readme)


@click.command(help=__doc__, name="generate-table")
@click.option("--commit/--no-commit", help="git commit changes to README.rst, if any.")
@click.option(
    "--readme-path",
    default="README.md",
    type=click.Path(dir_okay=False, file_okay=True),
    help="README.md file with addon table markers",
)
@click.option(
    "--addons-dir",
    default=".",
    type=click.Path(dir_okay=True, file_okay=False, exists=True),
    help="Directory containing several addons",
)
def main(commit, readme_path, addons_dir):  # noqa: C901
    """Generate or update the addons table in README.md."""

    if not os.path.isfile(readme_path):
        _logger.warning("%s not found", readme_path)
        return
    # list addons in . and __unported__
    addon_paths = []  # list of (addon_path, unported)
    for addon_path in os.listdir(addons_dir):
        addon_paths.append((addon_path, False))
    unported_directory = os.path.join("" if addons_dir == "." else addons_dir, "__unported__")
    if os.path.isdir(unported_directory):
        for addon_path in os.listdir(unported_directory):
            new_addon_path = os.path.join(unported_directory, addon_path)
            addon_paths.append((new_addon_path, True))
    addon_paths = sorted(addon_paths, key=lambda x: x[0])
    # load manifests
    header = ("addon", "version", "maintainers", "summary")
    rows_available = []
    rows_unported = []
    for addon_path, unported in addon_paths:
        for manifest_file in MANIFESTS:
            manifest_path = os.path.join(addon_path, manifest_file)
            has_manifest = os.path.isfile(manifest_path)
            if has_manifest:
                break
        if has_manifest:
            with open(manifest_path) as f:
                manifest = ast.literal_eval(f.read())
            addon_name = os.path.basename(addon_path)
            link = f"[{addon_name}]({addon_path}/)"
            version = manifest.get("version") or ""
            summary = manifest.get("summary") or manifest.get("name")
            summary = sanitize_cell(summary)
            installable = manifest.get("installable", True)
            if unported and installable:
                _logger.warning(f"{addon_path} is in __unported__ but is marked installable.")
                installable = False
            if installable:
                rows_available.append((link, version, render_maintainers(manifest), summary))
            else:
                rows_unported.append(
                    (
                        link,
                        version + " (unported)",
                        render_maintainers(manifest),
                        summary,
                    )
                )
    # replace table in README.md
    replace_in_readme(readme_path, header, rows_available, rows_unported)
    if commit:
        commit_if_needed(
            [readme_path],
            "[UPD] addons table in README.md",
        )
