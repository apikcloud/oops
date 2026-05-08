# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: scanner.py — oops/kb/scanner.py

"""AST-based scanner for Odoo source trees.

Produces raw dicts consumed by store.py for persistence.
No I/O other than reading source files — all path resolution
and tier detection is the caller's responsibility.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ODOO_BASE_CLASSES = {"Model", "TransientModel", "AbstractModel"}

FIELD_TYPES = {
    "Binary",
    "Boolean",
    "Char",
    "Date",
    "Datetime",
    "Float",
    "Html",
    "Image",
    "Integer",
    "Many2many",
    "Many2one",
    "Many2oneReference",
    "Monetary",
    "One2many",
    "Properties",
    "PropertiesDefinition",
    "Reference",
    "Selection",
    "Serialized",
    "Text",
}

# Marker strings used to identify tier roots from symlink real paths.
TIER_MARKERS = {
    "third-party": "/.third-party/",
    "apik": "/apik-addons/",
}

# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _parse_file(path: Path) -> ast.Module | None:
    """Parse a Python source file into an AST. Returns None on failure."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        log.warning("Syntax error in %s: %s", path, exc)
    except Exception as exc:
        log.warning("Cannot read %s: %s", path, exc)
    return None


def _extract_string_value(node: ast.expr) -> str | None:
    """Return the str value of a Constant or single-element List node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.List) and len(node.elts) == 1:
        return _extract_string_value(node.elts[0])
    return None


def is_odoo_model_class(node: ast.ClassDef) -> bool:
    """Return True if the class directly subclasses an Odoo model base."""
    for base in node.bases:
        name = None
        if isinstance(base, ast.Attribute):
            name = base.attr
        elif isinstance(base, ast.Name):
            name = base.id
        if name in ODOO_BASE_CLASSES:
            return True
    return False


def get_model_names(class_node: ast.ClassDef) -> tuple[str | None, list[str]]:
    """Extract _name and _inherit values from a class body.

    Returns:
        (_name value or None, list of _inherit values — empty if absent)
    """
    _name: str | None = None
    _inherit: list[str] = []

    for stmt in class_node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "_name":
                _name = _extract_string_value(stmt.value)
            elif target.id == "_inherit":
                val = stmt.value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    _inherit = [val.value]
                elif isinstance(val, ast.List):
                    _inherit = [
                        elt.value for elt in val.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
    return _name, _inherit


def is_field_assignment(stmt: ast.stmt) -> tuple[str, int] | None:
    """If stmt assigns a fields.XXX, return (field_name, line_no). Else None."""
    if not isinstance(stmt, ast.Assign):
        return None
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return None
    value = stmt.value
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Attribute) and func.attr in FIELD_TYPES:
            return stmt.targets[0].id, stmt.lineno
        if isinstance(func, ast.Name) and func.id in FIELD_TYPES:
            return stmt.targets[0].id, stmt.lineno
    return None


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------


def parse_manifest(manifest_path: Path) -> list[str]:
    """Extract the 'depends' list from an Odoo __manifest__.py via AST.

    Pure structural extraction — no eval(). Returns [] on any failure.
    """
    try:
        source = manifest_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(manifest_path))
    except (SyntaxError, OSError) as exc:
        log.debug("Cannot parse manifest %s: %s", manifest_path, exc)
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == "depends"):
                continue
            if isinstance(value, ast.List):
                return [elt.value for elt in value.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
        break  # only inspect the top-level dict

    return []


# ---------------------------------------------------------------------------
# ScanResult dataclass (plain dict for simplicity)
# ---------------------------------------------------------------------------
# ScanResult = {
#   "modules": {
#       module_name: {"origin": str, "depends": [str, ...]}
#   },
#   "symbols": [
#       {
#           "model":       str,
#           "name":        str,
#           "kind":        "field" | "method",
#           "origin":      str,
#           "module":      str,
#           "source_file": str,   # relative to tier_root
#           "source_line": int,
#       },
#       ...
#   ]
# }


def scan_module(
    module_dir: Path,
    origin: str,
    tier_root: Path,
) -> dict[str, Any]:
    """Scan a single Odoo module directory.

    Args:
        module_dir: absolute path to the module (must contain __manifest__.py).
        origin:     tier label ('odoo', 'enterprise', 'third-party', 'apik').
        tier_root:  root used to compute relative source_file paths.

    Returns:
        A ScanResult dict with keys 'modules' and 'symbols'.
    """
    module_name = module_dir.name
    result: dict[str, Any] = {"modules": {}, "symbols": []}

    # --- manifest ---
    manifest_path = module_dir / "__manifest__.py"
    if not manifest_path.exists():
        manifest_path = module_dir / "__openerp__.py"
    depends = parse_manifest(manifest_path) if manifest_path.exists() else []
    result["modules"][module_name] = {"origin": origin, "depends": depends}

    # --- models ---
    models_dir = module_dir / "models"
    if not models_dir.is_dir():
        return result

    for py_file in models_dir.rglob("*.py"):
        tree = _parse_file(py_file)
        if tree is None:
            continue

        try:
            rel_path = str(py_file.relative_to(tier_root))
        except ValueError:
            rel_path = str(py_file)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not is_odoo_model_class(node):
                continue

            _name, _inherit = get_model_names(node)

            # Determine which Odoo model(s) this class contributes to.
            target_models: list[str] = []
            if _name:
                target_models = [_name]
            elif _inherit:
                target_models = _inherit

            for model_name in target_models:
                for stmt in node.body:
                    # fields
                    field = is_field_assignment(stmt)
                    if field:
                        fname, lineno = field
                        result["symbols"].append(
                            {
                                "model": model_name,
                                "name": fname,
                                "kind": "field",
                                "origin": origin,
                                "module": module_name,
                                "source_file": rel_path,
                                "source_line": lineno,
                            }
                        )
                        continue
                    # methods
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        result["symbols"].append(
                            {
                                "model": model_name,
                                "name": stmt.name,
                                "kind": "method",
                                "origin": origin,
                                "module": module_name,
                                "source_file": rel_path,
                                "source_line": stmt.lineno,
                            }
                        )

    return result


def scan_tier(
    tier_root: Path,
    origin: str,
    allowed_modules: set[str] | None = None,
) -> dict[str, Any]:
    """Scan all addon modules under tier_root.

    Args:
        tier_root:       directory whose immediate children are Odoo modules.
        origin:          tier label.
        allowed_modules: if set, only modules whose name is in this set are scanned.

    Returns:
        Merged ScanResult for all scanned modules.
    """
    merged: dict[str, Any] = {"modules": {}, "symbols": []}

    if not tier_root.is_dir():
        log.warning("Tier root not found, skipping: %s", tier_root)
        return merged

    count = 0
    for entry in sorted(tier_root.iterdir()):
        if not entry.is_dir():
            continue
        if allowed_modules and entry.name not in allowed_modules:
            continue
        manifest = entry / "__manifest__.py"
        if not manifest.exists():
            manifest = entry / "__openerp__.py"
        if not manifest.exists():
            continue

        result = scan_module(entry, origin, tier_root)
        merged["modules"].update(result["modules"])
        merged["symbols"].extend(result["symbols"])
        count += 1

    log.info("  [%s] %s → %d modules", origin, tier_root, count)
    return merged


def odoo_addons_roots(odoo_path: Path) -> list[Path]:
    """Return the two standard addons roots inside an Odoo community tree.

    Odoo community keeps modules in two places:
    - <root>/addons/         standard modules (sale, account…)
    - <root>/odoo/addons/    core modules (base, web, mail…)

    Falls back to [odoo_path] if neither subdirectory exists.
    """
    candidates = [odoo_path / "addons", odoo_path / "odoo" / "addons"]
    roots = [p for p in candidates if p.is_dir()]
    if not roots:
        log.warning("No addons/ or odoo/addons/ found under %s — using path directly.", odoo_path)
        roots = [odoo_path]
    return roots


def resolve_symlink_tiers(
    repo_path: Path,
    allowed_modules: set[str] | None = None,
) -> dict[str, list[tuple[str, Path]]]:
    """Walk repo_path for symlinks and map each to its tier + real path.

    Returns:
        { origin: [(module_name, real_module_path), ...] }

    Tier assignment is based on the real path containing a known marker:
    - '/.third-party/'  → 'third-party'
    - '/apik-addons/'   → 'apik'
    Unrecognised symlinks are logged and skipped.
    """
    tiers: dict[str, list[tuple[str, Path]]] = {
        "third-party": [],
        "apik": [],
    }

    # Search at depth 1 under repo_path and its immediate non-hidden children.
    candidates: list[Path] = [repo_path]
    for child in repo_path.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            candidates.append(child)

    seen_real: set[Path] = set()

    for search_dir in candidates:
        if not search_dir.is_dir():
            continue
        try:
            entries = list(search_dir.iterdir())
        except PermissionError:
            continue
        for entry in entries:
            if not entry.is_symlink():
                continue
            real = Path(os.path.realpath(entry))
            if real in seen_real:
                continue
            seen_real.add(real)

            module_name = entry.name
            if allowed_modules and module_name not in allowed_modules:
                continue

            real_str = str(real)
            matched = False
            for origin, marker in TIER_MARKERS.items():
                if marker in real_str or marker.replace("/", "\\") in real_str:
                    tiers[origin].append((module_name, real))
                    matched = True
                    break
            if not matched:
                log.warning(
                    "Symlink %s → %s does not match any known tier root, skipping.",
                    entry,
                    real,
                )

    return tiers


def tier_root_from_real_path(origin: str, real_path: Path) -> Path | None:
    """Derive the tier root directory from a module's real path.

    e.g. /repo/.third-party/sale-workflow/sale_order_type
         → /repo/.third-party

    Returns None if the marker is not found in the path.
    """
    marker = TIER_MARKERS.get(origin)
    if not marker:
        return None
    real_str = str(real_path)
    idx = real_str.find(marker)
    if idx == -1:
        return None
    return Path(real_str[: idx + len(marker) - 1])
