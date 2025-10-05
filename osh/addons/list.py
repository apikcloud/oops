#!/usr/bin/env python3

import click

from osh.gitutils import load_repo, parse_gitmodules
from osh.helpers import find_addons
from osh.render import human_readable, render_boolean, render_table
from osh.utils import parse_repository_url


@click.command(name="list")
@click.option(
    "--format",
    type=click.Choice(["text", "json", "csv"]),
    default="text",
    show_default=True,
    help="Output format (default: text)",
)
@click.option(
    "--init/--no-init",
    is_flag=True,
    help="Run 'git submodule update --init' for submodules whose path is missing on disk",
)
@click.option(
    "--name",
    "-n",
    "submodules",
    multiple=True,
    help="Limit to these submodule names (as in .gitmodules)",
)
@click.option(
    "--symlinks-only",
    is_flag=True,
    help="Limit to these submodule names (as in .gitmodules)",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="List all addons, including those not in submodules (i.e. in the root of the repo)",
)
def main(format: str, init: bool, submodules: tuple, symlinks_only: bool, show_all: bool):  # noqa: C901, PLR0912
    """List all addons found in git submodules."""

    repo, gitmodules = load_repo()

    rows = []
    paths = []

    # gather submodules info
    subs = {}
    if gitmodules:
        for name, path, branch, url, pull_request in parse_gitmodules(gitmodules):
            canonical_url, _, _ = parse_repository_url(url) if url else ("", None, None)
            subs[path] = {
                "name": name,
                "path": path,
                "branch": branch or "",
                "url": canonical_url,
                "pr": pull_request,
            }

    for addon in find_addons(repo, shallow=not show_all):
        # FIXME: this is a bit of a hack, should be improved
        # skip duplicates (can happen if an addon is in a submodule and in the root)
        if addon.path in paths:
            continue

        paths.append(addon.path)

        sub = subs.get(addon.rel_path, {})

        rows.append(
            [
                addon.technical_name,
                render_boolean(addon.symlink),
                # human_readable(addon.rel_path, width=40),
                human_readable(sub.get("name", ""), width=30),
                human_readable(sub.get("branch", "")),
                render_boolean(sub.get("pr", False)),
                addon.version,
                human_readable(addon.author, width=30),
            ]
        )

    # sort by addon name
    rows.sort(key=lambda r: r[0])

    click.echo(
        render_table(
            rows,
            headers=["Addon", "S", "Submodule", "Upstream", "PR", "Version", "Author"],
            index=True,
        )
    )

    return 0

    # # Output
    # if format == "json":
    #     print(json.dumps(results, indent=2, ensure_ascii=False))
    # elif format == "csv":
    #     fields = ["addon", "submodule", "path", "submodule_path", "url", "branch"]
    #     w = csv.DictWriter(sys.stdout, fieldnames=fields)
    #     w.writeheader()
    #     for row in results:
    #         w.writerow(row)
    # else:
    #     if not results:
    #         click.echo("No addons found in local submodules.")
    #         return 0
    #     # compact text table
    #     click.echo(f"Found {len(results)} addon(s):")
    #     for r in results:
    #         click.echo(
    #             f"- {r['addon']:30}  [{r['submodule']}]  {r['path']}  (branch={r['branch'] or '-'})"
    #         )

    # return 0
