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
from pathlib import Path

import click
from git import GitCommandError
from oops.commands.base import command
from oops.core.config import config
from oops.core.paths import project_kb_path
from oops.io.file import parse_odoo_version
from oops.io.installed_modules import read_installed_modules
from oops.io.refactor import analyse_file, rewrite_file
from oops.kb import setup_kb_logging
from oops.kb.build import build_project_kb, is_project_kb_stale
from oops.kb.store import KBReader
from oops.services.git import commit, get_local_repo
from oops.utils.render import OopsError, print_rule, print_success, print_warning

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@command("refactor", help=__doc__)
@click.argument(
    "module_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--kb",
    "kb_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "Path to the project KB database. "
        "When set, --refresh is ignored and no auto-rebuild happens."
    ),
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
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Force a project KB rebuild before running, even if the KB looks fresh.",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(  # noqa: C901, PLR0912
    module_path: Path,
    kb_path: Path | None,
    branch: bool,
    dry_run: bool,
    refresh: bool,
    verbose: bool,
) -> None:
    setup_kb_logging(verbose)
    log = logging.getLogger(__name__)

    module_path = module_path.resolve()
    module_name = module_path.name

    # --- Locate repo (KB resolution always anchors there now) ---
    if kb_path is None:
        try:
            local_repo, repo_path = get_local_repo()
        except click.ClickException:
            raise OopsError(
                "oops refactor must run inside an oops project (no .git found)."
            ) from None

        # --- Resolve KB path ---
        kb_path = project_kb_path(repo_path)

        # --- Decide whether to build ---
        try:
            version = str(parse_odoo_version(repo_path).major_version)
        except (ValueError, OSError) as exc:
            raise OopsError(
                f"Could not read Odoo version from {config.project.file_odoo_version}."
            ) from exc

        stale, reason = is_project_kb_stale(repo_path, version)
        needs_build = refresh or stale

        if needs_build:
            info = read_installed_modules(repo_path)
            if info is None:
                raise OopsError(
                    f"installed_modules.txt not found at "
                    f"{repo_path / config.project.file_installed_modules}.\n"
                    "Create the file (one module per line) and re-run oops refactor."
                )
            why = "forced via --refresh" if refresh else f"stale: {reason}"
            log.info("Rebuilding project KB (%s)…", why)
            print_warning(f"Rebuilding project KB: {why}")
            try:
                kb_path = build_project_kb(repo_path, version, info.modules)
            except FileNotFoundError as exc:
                raise OopsError(str(exc)) from None
        elif not kb_path.exists():
            raise OopsError(f"Project KB not found: {kb_path}")
    else:
        # --kb was passed explicitly; skip all staleness logic.
        local_repo = None
        repo_path = None

    log.info("Using KB: %s", kb_path)

    print_rule(f"oops refactor — {module_name}")

    with KBReader(kb_path) as kb:
        modules_index = kb.get_modules()

        # --- Git branch ---
        branch_name = f"refactor/doc-{module_name}"
        if branch and not dry_run:
            if local_repo is None:
                try:
                    local_repo, repo_path = get_local_repo()
                except click.ClickException:
                    print_warning("Could not locate git repository — continuing without git.")
                    branch = False
            if local_repo is not None:
                try:
                    local_repo.git.checkout("-b", branch_name)
                    log.info("Created branch: %s", branch_name)
                except GitCommandError as exc:
                    print_warning("Could not create branch — continuing without git.")
                    log.debug("git checkout -b failed: %s", exc)
                    branch = False

        # --- Process model files ---
        models_dir = module_path / "models"
        if not models_dir.is_dir():
            print_warning(f"No models/ directory found in {module_path}")
            return

        py_files = sorted(models_dir.rglob("*.py"))
        if not py_files:
            print_warning("No .py files found in models/")
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
                    "  %s (%s): %d fields, %d methods (%d need docstring, %d overrides)",
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
                    click.echo(f"  would rewrite {rel}")
                continue

            original = py_file.read_text(encoding="utf-8", errors="replace")
            new_source = rewrite_file(py_file, classes)

            if new_source == original:
                log.debug("  No changes needed for %s", rel)
                continue

            py_file.write_text(new_source, encoding="utf-8")
            log.info("  Rewritten: %s", rel)
            total_rewrites += 1

            if branch and local_repo is not None and repo_path is not None:
                commit(
                    local_repo,
                    repo_path,
                    [str(py_file.relative_to(repo_path))],
                    "refactor_per_file",
                    module=module_name,
                    rel=str(rel),
                )

        if not dry_run:
            print_success(f"Done — {total_rewrites} file(s) rewritten.")
            if branch and total_rewrites:
                click.echo(f"  Branch: {branch_name}")
