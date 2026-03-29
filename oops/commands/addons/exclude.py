# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from __future__ import annotations

import click

from .tools import file_updater, get_content_from_manifest


@click.command("exclude")
def main():
    modules = get_content_from_manifest("author")

    default_exclusions = [
        r"^setup/|/static/description/index\.html$",
        ".svg$|/tests/([^/]+/)?cassettes/|^.copier-answers.yml$|^.github/|^eslint.config.cjs|^prettier.config.cjs",
        r"^README\.md$",
        "/static/(src/)?lib/",
        r"^docs/_templates/.*\.html$",
        r"readme/.*\.(rst|md)$",
        "/build/|/dist/",
        "/tests/samples/.*",
        "(LICENSE.*|COPYING.*)",
        ".third-party/",
        "third-party/",
    ]

    items = []

    for module, content in modules.items():
        if "apik" not in content.get("author", "").lower():
            items.append(module)

    indented_items = [f"  {item}" for item in default_exclusions + items]

    to_exclude_str = "|\n".join(indented_items)
    to_exclude_str = f"exclude: |\n  (?x)\n{to_exclude_str}"

    file_updater(
        filepath=".pre-commit-config.yaml",
        new_inner_content=to_exclude_str,
        start_tag="# [//]: # (exclude)",
        end_tag="# [//]: # (end exclude)",
        padding="\n",
    )
