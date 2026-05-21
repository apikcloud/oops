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

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.logger import live_progress, log
from oops.core.models import Result
from oops.core.paths import global_kb_dir
from oops.io.file import get_odoo_sources_dirs, list_odoo_sources_versions, parse_odoo_version
from oops.kb.build import _resolve_prototype_roles, _resolve_view_types
from oops.kb.scanner import odoo_addons_roots, scan_tier
from oops.kb.store import write_global_kb
from oops.kb.xml_scanner import scan_tier_xml
from oops.services.git import require_repository
from oops.utils.render import (
    conclude,
    get_console,
    make_table,
    metrics_grid,
    metrics_panel,
    print_warning,
    prompt_select,
    render_result,
    rule,
    warning_section,
)


@command("build-kb", help=__doc__)
@click.option(
    "--version",
    default=None,
    help=(
        "Odoo version string (e.g. 19.0). Defaults to the version declared in the current project's odoo_version.txt."
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

    print_warning("This command is experimental and may change without notice between releases.")
    console = get_console()

    if version is None:
        try:
            _, repo_path = require_repository()
            image_info = parse_odoo_version(repo_path)
            version = str(image_info.major_version)
        except (FileNotFoundError, click.ClickException, ValueError):
            versions = [item.version for item in list_odoo_sources_versions()]
            version = prompt_select("Available version(s):", versions)

            if not version:
                raise click.UsageError(
                    "Could not detect Odoo version from odoo_version.txt. Use --version to specify it explicitly."
                ) from None

    if cache_dir is None:
        cache_dir = global_kb_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / f"{version}.db"

    scan_results = []
    sources: dict[str, str] = {}
    summary = []
    scan_warnings: list[str] = []

    # Map filesystem directory names to semantic KB origin labels.
    # The sources dir uses "community" but the KB and drift filter expect "odoo".
    _ORIGIN_MAP = {"community": "odoo"}

    rule(f"Build global KB for Odoo {version}")

    # using Live for long-time processing
    with live_progress():
        for path in get_odoo_sources_dirs(version):
            name = _ORIGIN_MAP.get(path.name, path.name)

            log.info(f"Analyzing {name.capitalize()}...")

            if not path.exists():
                continue

            for root in odoo_addons_roots(path):
                result: Result[dict] = scan_tier(root, name)
                for w in result.warnings:
                    scan_warnings.append(f"[{name}] {w}")

                xml_result = scan_tier_xml(root, name)

                if result.data is None:
                    result.data = {}

                if xml_result.data is None:
                    xml_result.data = {}

                result.data["views"] = xml_result.data["views"]
                result.data["actions"] = xml_result.data["actions"]
                result.data["menus"] = xml_result.data["menus"]
                for w in xml_result.warnings:
                    scan_warnings.append(f"[{name}] {w}")

                scan_results.append(result.data)
                data = result.data or {}

                summary.append(
                    {
                        "name": name,
                        "path": root,
                        "modules": len(data.get("modules", {})),
                        "symbols": len(data.get("symbols", [])),
                        "field_refs": len(data.get("field_refs", [])),
                        "origins": len(data.get("model_origins", [])),
                        "views": len(data.get("views", [])),
                        "actions": len(data.get("actions", [])),
                        "menus": len(data.get("menus", [])),
                    }
                )

            sources[name] = str(path)

        log.info("Resolving prototype roles…")
        _resolve_prototype_roles(scan_results)

        log.info("Resolving view types…")
        _resolve_view_types(scan_results)

        log.info(f"Writing file to {db_path}")
        result = write_global_kb(
            db_path=db_path,
            odoo_version=version,
            sources=sources,
            scan_results=scan_results,
        )

    warning_section(scan_warnings)
    render_result(result)
    assert result.data is not None
    stats = result.data

    # Summary table
    t = make_table(
        title=None,
        columns=[
            ("Name", "brand.primary", "left"),
            ("Path", "dim", "left"),
            ("Modules", "green", "left"),
        ],
        rows=[
            [
                row["name"],
                str(row["path"]),
                str(row["modules"]),
            ]
            for row in summary
        ],
    )

    # Stats Panel
    p1 = metrics_panel(
        "Summary",
        [
            ["Modules", str(stats["modules"])],
            ["Symbols", str(stats["symbols"])],
            ["Fields", str(stats["fields"])],
            ["Methods", str(stats["methods"])],
            ["Views", str(stats["views"])],
            ["Actions", str(stats["actions"])],
            ["Menus", str(stats["menus"])],
        ],
    )

    rule("Results")
    console.print(metrics_grid(t, p1, ratios=[2, 1]))
    console.print()
    conclude(result.ok, "All done")
