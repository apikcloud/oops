# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: refactor.py — oops/commands/addons/refactor.py

"""oops-refactor — apply section headers and docstring skeletons to a custom module.

Operates on a single module at a time. Reads the project KB, classifies every
field and method in every model file, then rewrites each file in-place on a
dedicated git branch ready for PR review.

What the tool does
------------------
- Normalises section headers to the canonical `# === SECTION === #` format.
- Reorganises fields and methods into the section order defined in CONVENTIONS.md.
- Generates minimal Google-style docstring skeletons for every method that
  does not already have one.
- Inserts a class docstring skeleton on every new model class.
- Creates a git branch `refactor/doc-<module>` and commits each rewritten file.

What the tool does NOT do
-------------------------
- It never modifies method bodies.
- It never infers business intent.
- It never completes # TODO: markers.
- It never touches non-model Python files, XML, CSV, or __manifest__.py.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import click
from oops.io.refactor import analyse_file, rewrite_file
from oops.kb import setup_kb_logging
from oops.kb.store import KBReader
from rich.console import Console

console = Console()

CACHE_DIR_NAME = ".oops-cache"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)


def git_create_branch(repo_path: Path, branch_name: str) -> bool:
    result = _git(["checkout", "-b", branch_name], cwd=repo_path)
    if result.returncode != 0:
        logging.getLogger(__name__).error("git checkout -b %s failed:\n%s", branch_name, result.stderr)
        return False
    logging.getLogger(__name__).info("Created branch: %s", branch_name)
    return True


def git_commit_file(repo_path: Path, file_path: Path, message: str) -> bool:
    _git(["add", str(file_path)], cwd=repo_path)
    result = _git(["commit", "-m", message], cwd=repo_path)
    if result.returncode != 0:
        logging.getLogger(__name__).warning("git commit failed for %s:\n%s", file_path, result.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("refactor")
@click.argument(
    "module_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--kb",
    "kb_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the project KB database. Defaults to auto-detection from nearest .oops-cache/kb.db.",
)
@click.option(
    "--branch/--no-branch",
    default=True,
    show_default=True,
    help="Create a git branch and commit each rewritten file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print what would be changed without writing any file.",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(  # noqa: C901, PLR0912
    module_path: Path,
    kb_path: Path | None,
    branch: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Refactor the Odoo custom module at MODULE_PATH.

    Applies canonical section headers and minimal docstring skeletons to all
    model files, then commits the result on a dedicated git branch.
    """
    setup_kb_logging(verbose)
    log = logging.getLogger(__name__)

    module_path = module_path.resolve()
    module_name = module_path.name

    # --- Locate KB ---
    if kb_path is None:
        search = module_path
        while search != search.parent:
            candidate = search / CACHE_DIR_NAME / "kb.db"
            if candidate.exists():
                kb_path = candidate
                break
            search = search.parent

    if kb_path is None or not kb_path.exists():
        console.print(
            "[red]✗[/red] Project KB not found.\n"
            "Run [bold]oops-kb-build-project[/bold] first, or pass [bold]--kb[/bold]."
        )
        raise SystemExit(1)

    log.info("Using KB: %s", kb_path)

    # Locate repo root.
    repo_path = module_path.parent
    while repo_path != repo_path.parent:
        if (repo_path / ".git").exists():
            break
        repo_path = repo_path.parent

    console.rule(f"[bold]oops refactor[/bold] — {module_name}")

    with KBReader(kb_path) as kb:
        modules_index = kb.get_modules()

        # --- Git branch ---
        branch_name = f"refactor/doc-{module_name}"
        if branch and not dry_run:
            if not git_create_branch(repo_path, branch_name):
                console.print("[yellow]⚠[/yellow] Could not create branch — continuing without git.")
                branch = False

        # --- Process model files ---
        models_dir = module_path / "models"
        if not models_dir.is_dir():
            console.print(f"[yellow]⚠[/yellow] No models/ directory found in {module_path}")
            return

        py_files = sorted(models_dir.rglob("*.py"))
        if not py_files:
            console.print("[yellow]⚠[/yellow] No .py files found in models/")
            return

        total_rewrites = 0

        for py_file in py_files:
            rel = py_file.relative_to(module_path)
            log.info("Analysing %s…", rel)

            classes = analyse_file(py_file, kb, modules_index, module_name)
            if not classes:
                log.debug("  No Odoo model classes found, skipping.")
                continue

            for ci in classes:
                model_tag = ci.model_name or "+".join(ci.inherit) or "?"
                n_fields = sum(1 for s in ci.symbols if s.kind == "field")
                n_methods = sum(1 for s in ci.symbols if s.kind == "method")
                n_nodoc = sum(1 for s in ci.symbols if s.kind == "method" and not s.has_docstring)
                n_override = sum(1 for s in ci.symbols if s.is_override)
                log.info(
                    "  [cyan]%s[/cyan] (%s): %d fields, %d methods (%d need docstring, %d overrides)",
                    ci.class_name,
                    model_tag,
                    n_fields,
                    n_methods,
                    n_nodoc,
                    n_override,
                )

            if dry_run:
                new_source = rewrite_file(py_file, classes)
                if new_source != py_file.read_text(encoding="utf-8"):
                    console.print(f"  [dim]would rewrite[/dim] {rel}")
                continue

            original = py_file.read_text(encoding="utf-8", errors="replace")
            new_source = rewrite_file(py_file, classes)

            if new_source == original:
                log.debug("  No changes needed for %s", rel)
                continue

            py_file.write_text(new_source, encoding="utf-8")
            log.info("  [green]✓[/green] Rewritten: %s", rel)
            total_rewrites += 1

            if branch:
                msg = f"refactor({module_name}): add sections and docstrings to {rel}"
                git_commit_file(repo_path, py_file, msg)

        if not dry_run:
            console.print(f"\n[green]✓[/green] Done — {total_rewrites} file(s) rewritten.")
            if branch and total_rewrites:
                console.print(f"  Branch: [bold]{branch_name}[/bold]")
