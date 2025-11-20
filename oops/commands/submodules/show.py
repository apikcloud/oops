import click

from oops.git.core import GitRepository
from oops.git.gitutils import get_last_commit
from oops.utils.net import parse_repository_url
from oops.utils.render import format_datetime, human_readable, render_boolean, render_table


@click.command("show")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(dry_run: bool, no_commit: bool):
    """
    Update git submodules to their latest upstream versions.
    """

    repo = GitRepository()

    if not repo.has_gitmodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    rows = []
    for submodule in repo.parse_gitmodules():
        canonical_url, _, _ = (
            parse_repository_url(submodule.url) if submodule.url else ("", None, None)
        )
        row = [
            human_readable(submodule.name, width=50),
            canonical_url,
            submodule.branch,
            render_boolean(submodule.pr) or "",
        ]
        last_commit = get_last_commit(submodule.path)
        if last_commit:
            row += [
                format_datetime(last_commit.date),
                last_commit.age,
                # last_commit.author,
                last_commit.sha,
            ]
        else:
            row += ["no commit found", "--", "--", "--"]
        rows.append(row)

    if not rows:
        click.echo("No submodules found.")
        raise click.Abort()

    rows = sorted(rows, key=lambda x: x[0].lower())

    click.echo(
        render_table(
            rows,
            headers=["Name", "Url", "Upstream", "PR", "Last Commit", "Age", "SHA"],
            index=False,
        )
    )
