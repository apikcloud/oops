"""oops-kb-build-global — build the global Odoo KB (once per version).

Scans Odoo community (addons/ + odoo/addons/) and enterprise sources,
produces a SQLite database stored at:

    <cache_dir>/kb_global_<version>.db

where <cache_dir> defaults to ~/.cache/oops/kb/ and can be overridden
with --cache-dir to share the global KB across multiple project repos.

The global KB is version-specific and shared across all projects on the
same Odoo version — it should never be stored inside a project repository.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click
from oops.kb.scanner import odoo_addons_roots, scan_tier
from oops.kb.store import write_global_kb
from rich.console import Console
from rich.logging import RichHandler

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, markup=True)],
    )


@click.command("kb-build-global")
@click.option(
    "--odoo-path",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Root of the Odoo community repository (addons/ and odoo/addons/ are auto-detected).",
)
@click.option(
    "--enterprise-path",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Root of the Odoo enterprise repository (optional).",
)
@click.option(
    "--version",
    default="17.0",
    show_default=True,
    help="Odoo version string used in the output filename.",
)
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help=("Directory where kb_global_<version>.db is written. Defaults to ~/.cache/oops/kb/."),
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(
    odoo_path: Path,
    enterprise_path: Path | None,
    version: str,
    cache_dir: Path | None,
    verbose: bool,
) -> None:
    """Build the global Knowledge Base from Odoo community + enterprise sources.

    Run this once per Odoo version. The resulting database is shared across
    all projects on the same version.
    """
    _setup_logging(verbose)
    log = logging.getLogger(__name__)

    # Resolve output path.
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "oops" / "kb"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / f"kb_global_{version}.db"

    console.rule(f"[bold]oops kb-build-global[/bold] — Odoo {version}")

    scan_results = []
    sources: dict[str, str] = {}

    # --- Odoo community ---
    addons_roots = odoo_addons_roots(odoo_path)
    for root in addons_roots:
        log.info("Scanning [cyan]odoo[/cyan]: %s", root)
        result = scan_tier(root, "odoo")
        scan_results.append(result)
    sources["odoo"] = str(odoo_path)

    # --- Enterprise (optional) ---
    if enterprise_path:
        log.info("Scanning [cyan]enterprise[/cyan]: %s", enterprise_path)
        result = scan_tier(enterprise_path, "enterprise")
        scan_results.append(result)
        sources["enterprise"] = str(enterprise_path)

    # --- Write ---
    log.info("Writing global KB → %s", db_path)
    write_global_kb(
        db_path=db_path,
        odoo_version=version,
        sources=sources,
        scan_results=scan_results,
    )

    console.print(f"\n[green]✓[/green] Global KB ready: [bold]{db_path}[/bold]")
