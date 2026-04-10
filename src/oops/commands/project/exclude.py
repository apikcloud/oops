# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: exclude.py — oops/commands/project/exclude.py

r"""
Generate the exclusion list for pre-commit hooks in the .pre-commit-config.yaml file.
It checks all the addons in the root of the project and if the project is not owned by Apik, it excludes the addon.

The exclusion list uses a start and end tags to identify the section to update. The tags are the following:

- start: # oops:exclude:start
- end: # oops:exclude:end

The tags must be placed after the "(?x)" line in the "exclude" part of the .pre-commit-config file. Like this:
```text
exclude: |
  (?x)
  # oops:exclude:start
  # oops:exclude:end
  ^setup/|/static/description/index\.html$|
  .svg$|/tests/([^/]+/)?cassettes/|^.copier-answers.yml$|^.github/|^eslint.config.cjs|^prettier.config.cjs|
  ^README\.md$|
  /static/(src/)?lib/|
  ^docs/_templates/.*\.html$|
  readme/.*\.(rst|md)$|
  /build/|/dist/|
  /tests/samples/.*|
  (LICENSE.*|COPYING.*)|
  .third-party/|
  third-party/
```

Automatically, the modules to exclude will be added between the tags.

If the tags are not found in the file, nothing is done.
"""

from __future__ import annotations

import click
from oops.core.config import config
from oops.io.file import file_updater, find_addons
from oops.services.git import commit, get_local_repo


@click.command("exclude", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes.")
def main(dry_run: bool = False, no_commit: bool = False):
    repo, repo_path = get_local_repo()

    items = []
    precommit_file = config.precommit.file_precommit

    for addon in find_addons(repo_path, shallow=True):
        if config.manifest.author.lower() not in addon.author.lower():
            items.append(addon.technical_name)

    indented_items = [f"  {item}" for item in items]
    to_exclude_str = "|\n".join(indented_items) + ("|" if items else "")

    has_update = False
    if not dry_run:
        click.echo(f"Updating {precommit_file}...")
        has_update = file_updater(
            filepath=precommit_file,
            new_inner_content=to_exclude_str,
            start_tag="# oops:exclude:start",
            end_tag="# oops:exclude:end",
            padding="\n",
            append_position=False,
        )
    else:
        click.echo(f"It would update {precommit_file} with:\n{to_exclude_str}")

    if not no_commit and not dry_run and has_update:
        commit(repo, repo_path, [precommit_file], "pre_commit_exclude", skip_hooks=True)
