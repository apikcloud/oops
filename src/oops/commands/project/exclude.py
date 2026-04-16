# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: exclude.py — oops/commands/project/exclude.py

r"""
Generate the exclusion list for pre-commit hooks in the .pre-commit-config.yaml file.
It checks all the addons in the root of the project and if the project is not owned by `<manifest.author>`,
it excludes the addon.

The exclusion list uses a start and end tags to identify the section to update. The tags are the following:

- start: # oops:exclude:start
- end: # oops:exclude:end

The tags must be placed after the "(?x)" line in the "exclude" part of the .pre-commit-config file. Like this:
```yaml
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
from oops.commands.base import command
from oops.core.config import config
from oops.io.file import file_updater, get_excluded_addon_names
from oops.services.git import commit, get_local_repo


@command("exclude", help=__doc__)
@click.option("--dry-run", is_flag=True, help="Show what would happen, do nothing.")
@click.option("--no-commit", is_flag=True, help="Do not commit changes.")
@click.option("--fail", is_flag=True, help="Raise an error if the exclusion list is updated (pre-commit).")
def main(dry_run: bool = False, no_commit: bool = False, fail: bool = False):
    repo, repo_path = get_local_repo()

    addons = get_excluded_addon_names(repo_path)
    precommit_file = config.precommit.file_precommit

    def _format_item(item: str) -> str:
        return f"  {item}/|"

    content = "\n".join(_format_item(item) for item in addons) if addons else ""

    # TODO: make some noise if the tags are not found, to avoid confusion
    # maybe invite the user to run sync command before?
    has_update = file_updater(
        filepath=precommit_file,
        new_inner_content=content,
        start_tag="# oops:exclude:start",
        end_tag="# oops:exclude:end",
        padding="\n",
        append_position=False,
        dry_run=dry_run,
    )

    if not no_commit and not dry_run and has_update:
        commit(repo, repo_path, [precommit_file], "pre_commit_exclude", skip_hooks=True)

        if fail:
            raise click.ClickException("The list of exclusions has been updated, please run pre-commit again")
