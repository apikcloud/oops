# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: doc.py — oops/commands/project/doc.py

"""Generate a Markdown documentation site for the whole project.

Orchestrates the existing data sources — the addon inventory (the ``list``
data layer) and the IR v2 analysis (the ``analyze`` command) — and renders a
multi-file Markdown site: an index, one page per module, one page per model
(grouped by bare model name across modules), and audit pages with mermaid
graphs.

This command is read-only with respect to the project source. It rebuilds the
project KB if stale (same semantics as ``oops addons analyze``) but performs no
source rewriting, no git operations, and no manifest edits.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.exceptions import AppAbort, EarlyExit, OopsError
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import AddonInfo, Result
from oops.io.file import enrich_addon, find_addons
from oops.output.formatters import MarkdownSiteFormatter
from oops.output.sinks import deliver_site
from oops.services.git import list_submodules, require_repository
from oops.services.loc import get_addon_loc
from oops.services.project import require_project

from .presenters.doc import ProjectDocPresenter


def _build_inventory(
    repo,
    repo_path: Path,
    show_all: bool,
    names: tuple[str, ...],
) -> dict[str, dict]:
    """Stage A — reuse the ``list`` data layer to build a per-module inventory.

    Returns a mapping ``technical_name -> row`` where each row carries the
    addon's path plus the git-state facts (classification, location,
    submodule/branch/PR, LOC) used to enrich the documentation pages.
    """
    subs = list_submodules(repo)
    active_paths = {path for path, info in subs.items() if info["name"] in names} if names else None

    # Deduplicate by resolved path, preferring root-level symlinks over real
    # files (os.walk visits both when --all is used; see list.py).
    seen: dict[str, AddonInfo] = {}
    for addon in find_addons(repo_path, shallow=not show_all):
        if addon.path not in seen or addon.symlinked:
            seen[addon.path] = addon

    inventory: dict[str, dict] = {}
    for addon in seen.values():
        if active_paths is not None and addon.rel_path not in active_paths:
            continue

        log.info(f"Inventory of {addon.technical_name}")
        sub = subs.get(addon.rel_path, {})
        enrich_addon(addon, sub)
        loc = get_addon_loc(addon.path)

        inventory[addon.technical_name] = {
            "module": addon.technical_name,
            "path": addon.path,
            "location": addon.location,
            "symlink": addon.symlink,
            "submodule": addon.submodule or "",
            "branch": addon.branch or "",
            "pr": addon.pull_request or False,
            "version": addon.version,
            "classification": addon.classification,
            "author": addon.author,
            "loc": {
                "python": loc.python,
                "xml": loc.xml,
                "javascript": loc.javascript,
                "docs": loc.docs,
                "total": loc.total,
            },
        }

    return inventory


def _run_analyze(paths: list[str], refresh: bool) -> dict:
    """Stage B — orchestrate ``oops addons analyze`` in-process to temp JSON.

    ``standalone_mode=False`` stops Click from calling ``sys.exit`` so our
    ``OopsError`` (and friends) surface here. The IR v2 payload is read back
    from the temporary file.
    """
    from oops.cli import main as cli

    with tempfile.TemporaryDirectory() as tmp:
        tmp_json = Path(tmp) / "analyze.json"
        argv = ["addons", "analyze", *paths, "--format", "json", "--output-path", str(tmp_json)]
        if refresh:
            argv.append("--refresh")
        try:
            cli(argv, standalone_mode=False)
        except (OopsError, click.UsageError):
            raise
        except SystemExit as exc:  # pragma: no cover - defensive
            if exc.code not in (0, None):
                raise OopsError(f"analyze failed with exit code {exc.code}") from exc

        if not tmp_json.exists():
            raise OopsError("analyze produced no output — cannot generate documentation.")
        return json.loads(tmp_json.read_text(encoding="utf-8"))


@command(name="doc", help=__doc__)
@click.option(
    "--output-dir",
    "-o",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("oops-docs"),
    show_default=True,
    help="Target directory for the generated site. Created if absent.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include inactive addons (those not symlinked at the repo root).",
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Force a project KB rebuild before analysis (passed through to analyze).",
)
@click.option(
    "--name",
    "-n",
    "names",
    multiple=True,
    help="Limit to these submodule names (as in .gitmodules).",
)
@click.option(
    "--clean",
    is_flag=True,
    help="Wipe the output directory before writing.",
)
@click.pass_context
def main(
    ctx,
    output_dir: Path,
    show_all: bool,
    refresh: bool,
    names: tuple[str, ...],
    clean: bool,
) -> None:

    repo, repo_path = require_repository()
    require_project(repo_path)

    # --clean: wipe the output dir up front, confirming when it has content.
    if clean and output_dir.exists() and any(output_dir.iterdir()):
        if not click.confirm(f"Delete the contents of {output_dir}?"):
            raise AppAbort()
        shutil.rmtree(output_dir)

    result: Result[dict] = Result()

    with live_progress("Building inventory..."):
        inventory = _build_inventory(repo, repo_path, show_all, names)

    if not inventory:
        click.echo("No addons to document.", err=True)
        raise EarlyExit()

    with live_progress("Analysing modules..."):
        paths = [row["path"] for row in inventory.values()]
        ir = _run_analyze(paths, refresh)

    result.data = {"ir": ir, "inventory": inventory}
    for warning in ir.get("warnings", []):
        result.add_warning(warning)

    metadata = get_metadata()
    formatter = MarkdownSiteFormatter()
    output = ProjectDocPresenter().prepare(result, target=formatter.target, metadata=metadata)

    output_dir.mkdir(parents=True, exist_ok=True)
    deliver_site(formatter, output, output_dir)

    # Surface analyze warnings + recorded limitations once on stderr; the index
    # page carries the full detail.
    if result.warnings:
        click.echo(f"⚠ {len(result.warnings)} warning(s) — see {output_dir / 'index.md'}", err=True)
    for lim in ir.get("metadata", {}).get("limitations", []):
        click.echo(f"  note: {lim}", err=True)
