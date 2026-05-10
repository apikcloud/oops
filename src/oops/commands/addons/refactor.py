# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: refactor.py — oops/commands/addons/refactor.py

"""oops-refactor — apply section headers and docstring skeletons to custom modules.

Operates on one or more modules in a single run. Reads the project KB,
classifies every field and method in every model file, then rewrites each
file in-place. By default a dedicated git branch is created and one commit
per module is produced. Use --no-branch to stay on the current branch and
--no-commit to skip committing (edits are staged but not committed).

What the tool does
------------------
- Normalises section headers to the canonical `# === SECTION === #` format.
- Reorganises fields and methods into the section order defined in CONVENTIONS.md.
- Generates minimal Google-style docstring skeletons for every method that
  does not already have one.
- Inserts a class docstring skeleton on every new model class.
- Creates a git branch (`refactor/doc-<module>` for one module,
  `refactor/doc-multi` for several) and produces one commit per module
  whose body lists every rewritten file.

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
from oops.core.paths import global_kb_path, project_kb_path
from oops.io.file import parse_odoo_version
from oops.io.installed_modules import read_installed_modules
from oops.io.refactor import analyse_file, rewrite_file
from oops.kb import setup_kb_logging
from oops.kb.build import build_project_kb, compute_root_drift, is_project_kb_stale
from oops.kb.scanner import build_module_field_refs
from oops.kb.store import KBReader
from oops.services.git import commit, get_local_repo
from oops.utils.render import OopsError, human_readable, print_rule, print_success, print_warning

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@command("refactor", help=__doc__)
@click.argument(
    "module_paths",
    nargs=-1,
    required=True,
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
    help="Create a dedicated git branch before rewriting (use --no-commit to disable commits).",
)
@click.option(
    "--no-commit",
    is_flag=True,
    default=False,
    help="Do not commit changes.",
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
def main(  # noqa: C901, PLR0912, PLR0915
    module_paths: tuple[Path, ...],
    kb_path: Path | None,
    branch: bool,
    no_commit: bool,
    dry_run: bool,
    refresh: bool,
    verbose: bool,
) -> None:
    setup_kb_logging(verbose)
    log = logging.getLogger(__name__)

    for mp in module_paths:
        if mp.is_symlink():
            raise OopsError(
                f"{mp} is a symlink. Refactor cannot edit a symlinked "
                "module: it points to a third-party submodule or an apik-addons "
                "checkout, which must be refactored in its own repository.\n"
                "Run oops refactor inside the source repository instead."
            )

    resolved_paths = [mp.resolve() for mp in module_paths]

    # --- Locate repo (KB resolution always anchors there now) ---
    if kb_path is None:
        try:
            local_repo, repo_path = get_local_repo()
        except click.ClickException:
            raise OopsError(
                "oops refactor must run inside an oops project (no .git found)."
            ) from None

        kb_path = project_kb_path(repo_path)

        try:
            version = str(parse_odoo_version(repo_path).major_version)
        except (ValueError, OSError) as exc:
            raise OopsError(
                f"Could not read Odoo version from {config.project.file_odoo_version}."
            ) from exc

        # Read installed_modules.txt eagerly so we can both feed the build
        # and surface drift warnings on every run.
        info = read_installed_modules(repo_path)

        if info is not None:
            # Odoo community/enterprise modules are never at the repo root;
            # exclude them so only project-owned missing addons are surfaced.
            _gkb = global_kb_path(version)
            _odoo_mods: set[str] = set()
            if _gkb.exists():
                with KBReader(_gkb) as _kb:
                    _odoo_mods = {
                        n for n, d in _kb.get_modules().items()
                        if d["origin"] in {"odoo", "enterprise"}
                    }
            _project_modules = [m for m in info.modules if m not in _odoo_mods]

            missing, extra = compute_root_drift(repo_path, _project_modules)
            if missing:
                print_warning(
                    f"Modules in installed_modules.txt with no addon at the "
                    f"repo root: {missing}"
                )
            if extra:
                print_warning(
                    f"Addons at the repo root not in installed_modules.txt "
                    f"(will not be scanned by the project KB): {extra}"
                )

        stale, reason = is_project_kb_stale(repo_path, version)
        needs_build = refresh or stale

        if needs_build:
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

    branch_name = (
        f"refactor/doc-{resolved_paths[0].name}"
        if len(resolved_paths) == 1
        else "refactor/doc-multi"
    )

    with KBReader(kb_path) as kb:
        modules_index = kb.get_modules()

        # --- Git branch (one shared branch for the whole run) ---
        needs_repo = (branch or not no_commit) and not dry_run

        if needs_repo and local_repo is None:
            try:
                local_repo, repo_path = get_local_repo()
            except click.ClickException:
                print_warning("Could not locate git repository — continuing without git.")
                branch = False
                no_commit = True

        if branch and not dry_run and local_repo is not None:
            try:
                local_repo.git.checkout("-b", branch_name)
                log.info("Created branch: %s", branch_name)
            except GitCommandError as exc:
                print_warning("Could not create branch — continuing without commits.")
                log.debug("git checkout -b failed: %s", exc)
                branch = False
                no_commit = True

        grand_total = 0

        for module_path in resolved_paths:
            module_name = module_path.name
            print_rule(f"oops refactor — {module_name}")

            # --- Process model files ---
            models_dir = module_path / "models"
            if not models_dir.is_dir():
                print_warning(f"{module_name}: no models/ directory — skipping")
                continue

            py_files = sorted(models_dir.rglob("*.py"))
            if not py_files:
                print_warning(f"{module_name}: no .py files in models/ — skipping")
                continue

            # Build a module-level field→method ref index so cross-file links
            # within this module are visible to analyse_file().
            module_local_refs = build_module_field_refs(py_files)

            total_rewrites = 0
            rewritten_rels: list[str] = []

            for py_file in py_files:
                rel = py_file.relative_to(module_path)
                log.info("Analysing %s…", rel)

                classes = analyse_file(py_file, kb, modules_index, module_name, module_local_refs)
                if not classes:
                    log.debug("  No Odoo model classes found, skipping.")
                    continue

                for ci in classes:
                    model_tag = ci.model_name or "+".join(ci.inherit) or "?"
                    n_fields = sum(1 for s in ci.symbols if s.kind == "field")
                    n_methods = sum(1 for s in ci.symbols if s.kind == "method")
                    n_nodoc = sum(
                        1 for s in ci.symbols if s.kind == "method" and not s.has_docstring
                    )
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
                rewritten_rels.append(str(rel))

            if (
                not dry_run
                and rewritten_rels
                and local_repo is not None
                and repo_path is not None
            ):
                file_paths = [
                    str((module_path / rel).relative_to(repo_path))
                    for rel in rewritten_rels
                ]
                if no_commit:
                    local_repo.index.add([str(repo_path / f) for f in file_paths])
                else:
                    commit(
                        local_repo,
                        repo_path,
                        file_paths,
                        "refactor_per_module",
                        module=module_name,
                        description=human_readable(rewritten_rels, sep="\n"),
                    )

            grand_total += total_rewrites

        if not dry_run:
            print_success(
                f"Done — {grand_total} file(s) rewritten across {len(resolved_paths)} module(s)."
            )
            if branch and grand_total:
                click.echo(f"  Branch: {branch_name}")
