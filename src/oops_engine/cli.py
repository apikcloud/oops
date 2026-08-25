# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: cli.py — oops_engine/cli.py

"""oops-engine-scan — standalone entry point for scanning one already-checked-out
workspace directory and writing its results into a chosen backend under a given
repo_id.

No git/cloning/scheduling logic of its own — an existing third-party component
(e.g. a Kubernetes batch job) owns fetching the workspace. This is a standalone
``click.Command``, not wired into ``oops.cli``'s auto-discovery group: it is
meant to run as its own binary in a minimal container, independent of the local
CLI's config loading or telemetry.
"""

from __future__ import annotations

from pathlib import Path

import click
from oops_engine.pipeline import scan_repository
from oops_engine.store import write_kb


@click.command()
@click.argument("workspace_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--repo-id", required=True, help="Identity under which scanned rows are written.")
@click.option("--odoo-version", required=True, help="Odoo version string, e.g. '17.0'.")
@click.option("--backend", type=click.Choice(["sqlite", "postgres"]), default="sqlite", show_default=True)
@click.option(
    "--sqlite-path",
    type=click.Path(path_type=Path),
    default=None,
    help="SQLite file to write to (--backend sqlite). Defaults to ./<repo-id>.db.",
)
@click.option("--dsn", default=None, help="Postgres connection string, required when --backend=postgres.")
def main(
    workspace_path: Path,
    repo_id: str,
    odoo_version: str,
    backend: str,
    sqlite_path: "Path | None",
    dsn: "str | None",
) -> None:
    """Scan WORKSPACE_PATH and write results under --repo-id. No cloning, no scheduling."""
    if backend == "postgres":
        if not dsn:
            raise click.UsageError("--dsn is required when --backend=postgres")
        from oops_engine.backends.postgres import PostgresBackend  # noqa: PLC0415 — optional dependency

        be = PostgresBackend(dsn)
    else:
        from oops_engine.backends.sqlite import SQLiteBackend

        be = SQLiteBackend(sqlite_path or Path.cwd() / f"{repo_id}.db")

    result = scan_repository(workspace_path, repo_id)
    if not result.ok:
        for err in result.errors:
            click.echo(err, err=True)
        raise SystemExit(1)

    write_result = write_kb(be, repo_id, odoo_version, result.data or [], sources={repo_id: str(workspace_path)})
    if not write_result.ok:
        for err in write_result.errors:
            click.echo(err, err=True)
        raise SystemExit(1)
    click.echo(f"Wrote KB for repo_id={repo_id!r}")


if __name__ == "__main__":
    main()
