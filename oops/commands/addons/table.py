# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from __future__ import annotations

import click
from tabulate import tabulate

from .tools import file_updater, get_content_from_manifest


@click.command("table")
def main():
    def _get_github_user(_user):
        return (
            f"<a href='https://github.com/{_user}'>"
            f"<img src='https://github.com/{_user}.png' width='32' height='32' alt='{_user}'/></a>"
        )

    modules = get_content_from_manifest("name,version,maintainers,summary")
    structure = []
    for module in modules:
        row = [f"[{module}](/{module})"]
        values = modules[module]

        row.append(values.get("version", ""))

        if addon_maintainers := values.get("maintainers"):
            addon_maintainers = [_get_github_user(user) for user in addon_maintainers]
            row.append(" ".join(addon_maintainers))
        else:
            row.append("")

        row.append(" ".join(values.get("summary", "").split()))

        structure.append(row)

    headers = ["Addon", "Version", "Maintainers", "Summary"]

    table = tabulate(structure, headers=headers, tablefmt="github")

    new_content = f"Available addons\n----------------\n{table}\n"

    # We keep using OCA tags, in case we want to use their tools again.
    # Start tag: # [//]: # (addons)
    # End tag: # [//]: # (end addons)
    file_updater(
        filepath="README.md",
        new_inner_content=new_content,
        start_tag="[//]: # (addons)",
        end_tag="[//]: # (end addons)",
        padding="\n\n",
    )
