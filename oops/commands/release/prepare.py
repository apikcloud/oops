# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: prepare.py — oops/commands/release/prepare.py

"""
Prepare a release: update CHANGELOG, write migration script, commit, and tag.

\b
Workflow:
  1. Compute the next version (minor by default, or --major / --fix / --version).
  2. Validate that CHANGELOG.md has a non-empty [Unreleased] section.
  3. Replace [Unreleased] with the versioned header and today's date.
  4. Write the migration script for addon changes since the last tag.
  5. Commit all staged files and create an annotated git tag.

Use --dry-run to preview without writing anything.
"""

from datetime import date

import click

from oops.commands.base import command
from oops.io.file import get_addons_diff, make_migration_command, write_migration_script
from oops.services.git import commit, get_local_repo
from oops.utils.render import print_success, print_warning
from oops.utils.versioning import get_last_release, get_next_releases, is_valid_semver


def _update_changelog(text: str, version: str) -> str:
    """Replace the [Unreleased] header in a CHANGELOG with the versioned release header.

    Args:
        text: Full CHANGELOG.md content.
        version: Version string (e.g. "v1.3.0") to substitute.

    Returns:
        Updated CHANGELOG content.

    Raises:
        click.ClickException: If no [Unreleased] section exists or it contains no entries.
    """
    lines = text.splitlines(keepends=True)

    unreleased_idx = None
    next_section_idx = None

    for i, line in enumerate(lines):
        if line.strip().lower() == "## [unreleased]":
            unreleased_idx = i
        elif unreleased_idx is not None and line.startswith("## [") and i > unreleased_idx:
            next_section_idx = i
            break

    if unreleased_idx is None:
        raise click.ClickException("CHANGELOG.md has no [Unreleased] section.")

    section = lines[unreleased_idx + 1 : next_section_idx]
    if not any(l.strip().startswith("-") for l in section):
        raise click.ClickException("The [Unreleased] section in CHANGELOG.md is empty.")

    version_clean = version.lstrip("v")
    lines[unreleased_idx] = f"## [{version_clean}] - {date.today().isoformat()}\n"

    return "".join(lines)


@command(name="prepare", help=__doc__)
@click.option("--major", "bump", flag_value="major", help="Bump major version.")
@click.option(
    "--minor", "bump", flag_value="minor", default=True, help="Bump minor version (default)."
)
@click.option("--fix", "bump", flag_value="fix", help="Bump fix/patch version.")
@click.option(
    "--version", "version_override", default=None, help="Set version manually (e.g. v1.3.0)."
)
@click.option("--no-commit", is_flag=True, help="Stage changes but do not commit or tag.")
@click.option("--no-tag", is_flag=True, help="Commit but do not create a git tag.")
@click.option("--dry-run", is_flag=True, help="Show planned changes without writing anything.")
def main(
    bump: str,
    version_override: str,
    no_commit: bool,
    no_tag: bool,
    dry_run: bool,
):
    repo, repo_path = get_local_repo()

    # 1. Resolve next version
    if version_override:
        if not is_valid_semver(version_override):
            raise click.ClickException(
                f"Invalid semver format: {version_override!r}. Expected vX.Y.Z."
            )
        version = version_override
    else:
        try:
            minor, fix, major = get_next_releases()
        except ValueError as error:
            raise click.ClickException(
                f"{error}. Use --version to specify the version for the first release."
            ) from error
        version = {"minor": minor, "fix": fix, "major": major}[bump]

    click.echo(f"Preparing release {version}")

    # 2. Commits ahead of last tag
    last_tag = get_last_release()
    if last_tag:
        commits_ahead = list(repo.iter_commits(f"{last_tag}..HEAD"))
        base_ref = last_tag
        click.echo(f"{len(commits_ahead)} commit(s) ahead of {last_tag}")
    else:
        commits_ahead = list(repo.iter_commits("HEAD"))
        base_ref = repo.git.rev_list("--max-parents=0", "HEAD").strip()

    has_new_commits = bool(commits_ahead)

    # 3. Update CHANGELOG
    changelog_path = repo_path / "CHANGELOG.md"
    if not changelog_path.exists():
        raise click.ClickException("CHANGELOG.md not found.")

    updated_changelog = _update_changelog(changelog_path.read_text(encoding="utf-8"), version)

    if dry_run:
        click.echo(
            f"[dry-run] CHANGELOG.md → ## [{version.lstrip('v')}] - {date.today().isoformat()}"
        )
    else:
        changelog_path.write_text(updated_changelog, encoding="utf-8")
        print_success(f"CHANGELOG.md updated → {version}")

    # 4. Migration script
    staged: list[str] = ["CHANGELOG.md"]

    if has_new_commits:
        new_addons, updated_addons, removed_addons = get_addons_diff(repo, base_ref)
        if any([new_addons, updated_addons, removed_addons]):
            content = make_migration_command(
                new_addons, updated_addons, removed_addons, release=version
            )
            if dry_run:
                click.echo("[dry-run] Would write migration script")
                click.echo(content)
            else:
                script_path = write_migration_script(content)
                if script_path:
                    staged.append(script_path)
                    print_success(f"Migration script written → {script_path}")
        else:
            print_warning("No addon changes detected — migration script skipped.")
    else:
        print_warning("No commits ahead of last tag — migration script skipped.")

    if dry_run:
        raise click.exceptions.Exit(0)

    # 5. Commit
    if not no_commit:
        commit(repo, repo_path, staged, "release_prepare", version=version)

    # 6. Tag
    if not no_commit and not no_tag:
        tag_obj = repo.create_tag(version, message=version, ref=repo.head.commit.hexsha)
        print_success(f"Tagged {tag_obj.name}")
    elif no_tag:
        print_warning(f"Skipped tag (--no-tag). Run: git tag -a {version} -m {version!r}")
