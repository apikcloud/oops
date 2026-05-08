"""oops-kb-build-project — build the project KB for a client repository.

Merges the global KB with third-party and apik modules found via symlink
resolution, filtered to the installed module list, and writes:

    <repo>/.oops-cache/kb_project_<version>.db

The global KB path is resolved automatically from ~/.cache/oops/kb/ unless
overridden with --global-kb.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from oops.kb.scanner import (
    resolve_symlink_tiers,
    scan_module,
    tier_root_from_real_path,
)
from oops.kb.store import KBReader, write_project_kb
from rich.console import Console
from rich.logging import RichHandler

console = Console()

CACHE_DIR_NAME = ".oops-cache"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, markup=True)],
    )


def _load_modules_list(modules_file: Path) -> set[str] | None:
    """Load module names from a text file (one per line, # comments ignored)."""
    if not modules_file.exists():
        return None
    lines = modules_file.read_text(encoding="utf-8").splitlines()
    return {l.strip() for l in lines if l.strip() and not l.startswith("#")}


def _default_global_kb(version: str) -> Path:
    return Path.home() / ".cache" / "oops" / "kb" / f"kb_global_{version}.db"


@click.command("kb-build-project")
@click.argument(
    "repo_path",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--version",
    default="17.0",
    show_default=True,
    help="Odoo version string — used to locate the global KB and name the output file.",
)
@click.option(
    "--global-kb",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=("Path to the global KB database. Defaults to ~/.cache/oops/kb/kb_global_<version>.db."),
)
@click.option(
    "--modules",
    "modules_file",
    default=None,
    type=click.Path(path_type=Path),
    help=(
        "Text file listing installed module names (one per line). "
        "If omitted, all modules found via symlinks are indexed."
    ),
)
@click.option(
    "--slug",
    default=None,
    help="Project slug embedded in KB metadata. Defaults to the repo directory name.",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(
    repo_path: Path,
    version: str,
    global_kb: Path | None,
    modules_file: Path | None,
    slug: str | None,
    verbose: bool,
) -> None:
    """Build the project Knowledge Base for the Odoo client repository at REPO_PATH.

    REPO_PATH defaults to the current directory.

    Merges the global KB (Odoo community + enterprise) with third-party and
    apik modules detected from symlinks in the repository, filtered to the
    installed module list.

    Output: <REPO_PATH>/.oops-cache/kb_project_<version>.db
    """
    _setup_logging(verbose)
    log = logging.getLogger(__name__)

    repo_path = repo_path.resolve()
    project = slug or repo_path.name

    # Resolve global KB.
    if global_kb is None:
        global_kb = _default_global_kb(version)
    if not global_kb.exists():
        console.print(f"[red]✗[/red] Global KB not found: {global_kb}\nRun [bold]oops-kb-build-global[/bold] first.")
        sys.exit(1)

    # Output path inside the repo cache.
    cache_dir = repo_path / CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / f"kb_project_{version}.db"

    console.rule(f"[bold]oops kb-build-project[/bold] — {project} / Odoo {version}")

    # Load module filter.
    allowed_modules: set[str] | None = None
    if modules_file:
        allowed_modules = _load_modules_list(modules_file)
        if allowed_modules:
            log.info("Module filter: %d modules from %s", len(allowed_modules), modules_file)
        else:
            log.warning("Modules file empty or not found: %s — no filter applied", modules_file)
            allowed_modules = None

    # --- Seed from global KB ---
    log.info("Loading global KB: %s", global_kb)
    with KBReader(global_kb) as kb:
        global_meta = kb.get_meta()
        global_sources = kb.get_sources()
        # Re-export global data as a scan result so write_project_kb can ingest it.
        global_modules = kb.get_modules()
        global_symbols = []
        for model_row in kb.get_model_symbols(model=""):
            pass  # handled below via raw query
        # Use a raw query to get all symbols efficiently.
        rows = kb._con.execute(
            "SELECT model, name, kind, origin, module, source_file, source_line FROM symbols"
        ).fetchall()
        for r in rows:
            global_symbols.append(dict(r))

    global_scan = {
        "modules": global_modules,
        "symbols": global_symbols,
    }

    global_odoo_version = global_meta.get("odoo_version", version)
    sources: dict[str, str] = dict(global_sources)

    # --- Scan project tiers (symlinks) ---
    symlink_tiers = resolve_symlink_tiers(repo_path, allowed_modules)

    # Scan order: apik first, then third-party.
    # third-party has higher precedence and its entries will override apik
    # for the same (model, name, kind, module) primary key via INSERT OR REPLACE.
    tier_scan_order = ["apik", "third-party"]
    project_scan_results: list[dict] = []
    all_project_modules: set[str] = set()

    for origin in tier_scan_order:
        modules_in_tier = symlink_tiers.get(origin, [])
        if not modules_in_tier:
            continue

        log.info("Scanning [cyan]%s[/cyan] tier (%d modules)…", origin, len(modules_in_tier))
        scanned = 0

        # Determine tier_root from the first resolved path.
        tier_root = None
        for _mod_name, real_path in modules_in_tier:
            tier_root = tier_root_from_real_path(origin, real_path)
            if tier_root:
                break

        if tier_root is None:
            log.warning("Could not determine tier root for %s, skipping.", origin)
            continue

        sources[origin] = str(tier_root)

        tier_result: dict = {"modules": {}, "symbols": []}
        for module_name, real_module_path in modules_in_tier:
            manifest = real_module_path / "__manifest__.py"
            if not manifest.exists():
                manifest = real_module_path / "__openerp__.py"
            if not manifest.exists():
                log.debug("No manifest in %s, skipping.", real_module_path)
                continue

            result = scan_module(real_module_path, origin, tier_root)
            tier_result["modules"].update(result["modules"])
            tier_result["symbols"].extend(result["symbols"])
            all_project_modules.add(module_name)
            scanned += 1

        log.info("  → %d modules scanned", scanned)
        project_scan_results.append(tier_result)

    # --- Scope ---
    scope = sorted(allowed_modules) if allowed_modules else sorted(all_project_modules)

    # --- Write ---
    log.info("Writing project KB → %s", db_path)
    write_project_kb(
        db_path=db_path,
        odoo_version=global_odoo_version,
        project=project,
        scope=scope,
        sources=sources,
        scan_results=[global_scan] + project_scan_results,
    )

    console.print(f"\n[green]✓[/green] Project KB ready: [bold]{db_path}[/bold]")
    console.print(f"  Project : {project}")
    console.print(f"  Scope   : {len(scope)} modules")
