# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: build_global.py — oops/commands/misc/build_global.py

"""oops misc build-kb — build the global Odoo KB (once per version).

EXPERIMENTAL — This command is part of the KB pipeline. Its interface may
change without notice between releases.

Scans Odoo community (addons/ + odoo/addons/) and enterprise sources from the
standard oops source directories (config.odoo.sources_dir/<version>/), and
produces a SQLite database stored at:

    <cache_dir>/<version>.db

where <cache_dir> defaults to ~/.cache/oops/kb/.

The global KB is version-specific and shared across all projects on the
same Odoo version — it should never be stored inside a project repository.
Run this once per Odoo version. The resulting database is shared across all
projects on the same version.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.paths import global_kb_dir
from oops.io.file import get_odoo_sources_dirs, parse_odoo_version
from oops.kb import setup_kb_logging
from oops.kb.build import _resolve_prototype_roles
from oops.kb.scanner import odoo_addons_roots, scan_tier
from oops.kb.store import write_global_kb
from oops.services.git import get_local_repo
from oops.utils.render import print_rule, print_success, print_warning


@command("build-kb", help=__doc__)
@click.option(
    "--version",
    default=None,
    help=(
        "Odoo version string (e.g. 17.0). "
        "Defaults to the version declared in the current project's odoo_version.txt."
    ),
)
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory where <version>.db is written. Defaults to ~/.cache/oops/kb/.",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(
    version: str | None,
    cache_dir: Path | None,
    verbose: bool,
) -> None:
    setup_kb_logging(verbose)
    print_warning(
        "This command is experimental and may change without notice between releases."
    )
    log = logging.getLogger(__name__)

    if version is None:
        try:
            _, repo_path = get_local_repo()
            image_info = parse_odoo_version(repo_path)
            version = str(image_info.major_version)
        except (click.ClickException, ValueError):
            raise click.UsageError(
                "Could not detect Odoo version from odoo_version.txt. "
                "Use --version to specify it explicitly."
            ) from None

    community_dir, enterprise_dir = get_odoo_sources_dirs(version)

    if cache_dir is None:
        cache_dir = global_kb_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / f"{version}.db"

    print_rule(f"oops misc build-kb — Odoo {version}")

    scan_results = []
    sources: dict[str, str] = {}

    # --- Odoo community ---
    addons_roots = odoo_addons_roots(community_dir)
    for root in addons_roots:
        log.info("Scanning odoo: %s", root)
        result = scan_tier(root, "odoo")
        scan_results.append(result)
    sources["odoo"] = str(community_dir)

    # --- Enterprise (optional) ---
    if enterprise_dir.exists():
        log.info("Scanning enterprise: %s", enterprise_dir)
        result = scan_tier(enterprise_dir, "enterprise")
        scan_results.append(result)
        sources["enterprise"] = str(enterprise_dir)

    log.info("Resolving prototype roles…")
    _resolve_prototype_roles(scan_results)

    # --- Write ---
    log.info("Writing global KB → %s", db_path)
    write_global_kb(
        db_path=db_path,
        odoo_version=version,
        sources=sources,
        scan_results=scan_results,
    )

    print_success(f"Global KB ready: {db_path}")
