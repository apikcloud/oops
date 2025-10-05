import click

from osh.gitutils import get_last_commit, load_repo, parse_gitmodules
from osh.net import parse_repository_url
from osh.render import format_datetime, human_readable, render_boolean, render_table


@click.command("show")
@click.option("--dry-run", is_flag=True, help="Show planned changes only")
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
def main(dry_run: bool, no_commit: bool):
    """
    Update git submodules to their latest upstream versions.
    """

    _, gitmodules = load_repo()

    if not gitmodules:
        click.echo("No .gitmodules found.")
        raise click.Abort()

    rows = []
    for name, path, branch, url, pull_request in parse_gitmodules(gitmodules):
        canonical_url, _, _ = parse_repository_url(url) if url else ("", None, None)
        row = [
            human_readable(name, width=50),
            canonical_url,
            branch,
            render_boolean(pull_request) or "",
        ]
        last_commit = get_last_commit(path)
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
