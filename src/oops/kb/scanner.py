# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: scanner.py — oops/kb/scanner.py

"""AST-based scanner for Odoo source trees.

Sections:
    - Constants: ODOO_BASE_CLASSES, FIELD_TYPES, METHOD_SECTION_*, tier marker helpers
    - AST helpers: parse, extract, classify Odoo model nodes
    - Manifest parsing: delegated to oops.io.manifest
    - Scanning: scan_module, scan_tier, odoo_addons_roots
    - Root addon discovery: discover_root_addons, tier_root_from_real_path
"""

import ast
import json
from pathlib import Path
from typing import Set

from oops.core.compat import Any, Dict, Iterable, List, Optional, Tuple, Union
from oops.core.config import config
from oops.core.logger import log
from oops.core.models import Result
from oops.io.manifest import load_manifest

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

# Field kwargs whose string-literal value is a method name.
FIELD_REF_KWARGS = ("compute", "inverse", "search", "default", "selection")

# ---------------------------------------------------------------------------
# Method section name constants (source of truth; refactor.py imports these)
# ---------------------------------------------------------------------------

METHOD_SECTION_CRUD = "CRUD METHODS"
METHOD_SECTION_COMPUTE = "COMPUTE METHODS"
METHOD_SECTION_SELECTION = "SELECTION METHODS"
METHOD_SECTION_DEFAULT = "DEFAULT METHODS"
METHOD_SECTION_ONCHANGE = "ONCHANGE METHODS"
METHOD_SECTION_CONSTRAINT = "CONSTRAINT METHODS"
METHOD_SECTION_HELPER = "HELPER METHODS"
METHOD_SECTION_ACTION = "ACTION METHODS"
METHOD_SECTION_BUSINESS = "BUSINESS METHODS"

# ORM methods whose section is fully determined by name.
CRUD_NAMES = {"create", "write", "unlink", "copy", "name_search", "_search"}
DEFAULT_NAMES = {"default_get"}

# Maps a field kwarg to the section its target method should be placed in.
KWARG_TO_SECTION: Dict[str, str] = {
    "compute": METHOD_SECTION_COMPUTE,
    "inverse": METHOD_SECTION_COMPUTE,
    "search": METHOD_SECTION_COMPUTE,
    "default": METHOD_SECTION_DEFAULT,
    "selection": METHOD_SECTION_SELECTION,
}


def _tier_markers() -> dict:
    """Build tier path markers from config.submodules paths."""
    return {
        "third-party": f"/{config.submodules.current_path}/",
        "apik": f"/{config.submodules.apik_path}/",
    }


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _parse_file(path: Path) -> Optional[ast.Module]:
    """Parse a Python source file into an AST. Returns None on failure."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        log.warning("Syntax error in %s: %s", path, exc)
    except Exception as exc:
        log.warning("Cannot read %s: %s", path, exc)
    return None


def _extract_string_value(node: ast.expr) -> Optional[str]:
    """Return the str value of a Constant or single-element List node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.List) and len(node.elts) == 1:
        return _extract_string_value(node.elts[0])
    return None


def is_odoo_model_class(node: ast.ClassDef) -> bool:
    """Return True if the class directly subclasses an Odoo model base.

    Returns:
        True if any base class name is in ``ODOO_BASE_CLASSES``, False otherwise.
    """
    for base in node.bases:
        name = None
        if isinstance(base, ast.Attribute):
            name = base.attr
        elif isinstance(base, ast.Name):
            name = base.id
        if name in ODOO_BASE_CLASSES:
            return True
    return False


def get_model_names(class_node: ast.ClassDef) -> Tuple[Optional[str], List[str]]:
    """Extract _name and _inherit values from a class body.

    Returns:
        (_name value or None, list of _inherit values — empty if absent)
    """
    _name: Optional[str] = None
    _inherit: List[str] = []

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


def get_model_type(node: ast.ClassDef) -> str:
    """Return the Odoo model kind for a class node.

    Returns:
        ``'abstract'``, ``'transient'``, or ``'model'``.
    """
    for base in node.bases:
        name = None
        if isinstance(base, ast.Attribute):
            name = base.attr
        elif isinstance(base, ast.Name):
            name = base.id
        if name == "AbstractModel":
            return "abstract"
        if name == "TransientModel":
            return "transient"
    return "model"


def get_inherits(class_node: ast.ClassDef) -> Dict[str, str]:
    """Extract _inherits dict {parent_model: fk_field} from a class body.

    Returns:
        Mapping of parent model name to the local FK field name, empty if absent.
    """
    for stmt in class_node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if not isinstance(target, ast.Name) or target.id != "_inherits":
                continue
            val = stmt.value
            if not isinstance(val, ast.Dict):
                continue
            result: Dict[str, str] = {}
            for k, v in zip(val.keys, val.values):
                if (
                    isinstance(k, ast.Constant)
                    and isinstance(k.value, str)
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, str)
                ):
                    result[k.value] = v.value
            return result
    return {}


def get_description(class_node: ast.ClassDef) -> Optional[str]:
    """Return the literal ``_description = "..."`` string, or None."""
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_description" for t in stmt.targets
        ):
            return _extract_string_value(stmt.value)
    return None


def is_field_assignment(stmt: ast.stmt) -> Optional[Tuple[str, int, str]]:
    """If stmt assigns a fields.XXX, return (field_name, lineno, field_type). Else None.

    Args:
        stmt: An AST statement node to inspect.

    Returns:
        ``(field_name, lineno, field_type)`` if the statement is a single-target
        ``fields.XXX(...)`` assignment, ``None`` otherwise.
    """
    if not isinstance(stmt, ast.Assign):
        return None
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return None
    value = stmt.value
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Attribute) and func.attr in FIELD_TYPES:
            return stmt.targets[0].id, stmt.lineno, func.attr
        if isinstance(func, ast.Name) and func.id in FIELD_TYPES:
            return stmt.targets[0].id, stmt.lineno, func.id
    return None


def extract_field_refs(stmt: ast.Assign) -> Dict[str, str]:
    """Return {kwarg: target_method_name} for string-literal kwargs in FIELD_REF_KWARGS.

    Args:
        stmt: An AST ``Assign`` node for a field declaration.

    Returns:
        Mapping of kwarg name to the referenced method name string.

    Bare callables and lambdas are skipped silently.
    """
    refs: Dict[str, str] = {}
    if not isinstance(stmt.value, ast.Call):
        return refs
    for kw in stmt.value.keywords:
        if kw.arg in FIELD_REF_KWARGS and isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, str):
                refs[kw.arg] = kw.value.value
    return refs


# ---------------------------------------------------------------------------
# IR v2 content extraction (additive — the rewriter does not use these)
# ---------------------------------------------------------------------------

# Relational field types take their comodel as positional arg 0.
_RELATIONAL_TYPES = {"Many2one", "One2many", "Many2many", "Many2oneReference", "Reference"}

# Kwargs whose non-literal value flags the field as ``dynamic`` (spec §8.4).
_DYNAMIC_SENSITIVE = {"string", "help", "default", "selection"}


def _unparse(node: ast.AST) -> Optional[str]:
    """Return ``ast.unparse(node)`` when available (py3.9+), else ``None``."""
    fn = getattr(ast, "unparse", None)
    if fn is None:
        return None
    try:
        return fn(node)
    except Exception:
        return None


def _translation_wrapped(node: ast.expr) -> Optional[ast.expr]:
    """If ``node`` is a ``_("literal")`` translation call, return its first arg."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_"
        and len(node.args) >= 1
    ):
        return node.args[0]
    return None


def _literal_or_none(node: ast.expr) -> Tuple[Any, bool]:
    """Return ``(value, is_dynamic)`` for a kwarg value node.

    ``value`` is the Python literal when ``node`` is a constant (optionally
    wrapped in ``_()``), else ``None``. ``is_dynamic`` is ``True`` when the node
    is present but non-literal (variable, f-string, call other than ``_()``,
    comprehension, …). Never evaluates.
    """
    inner = _translation_wrapped(node)
    if inner is not None:
        node = inner
    if isinstance(node, ast.Constant):
        return node.value, False
    return None, True


def _literal_selection(node: ast.expr) -> Tuple[Optional[List[list]], bool]:
    """Return ``(pairs, is_dynamic)`` for a ``selection=`` list-of-pairs literal.

    Returns ``(None, True)`` for any non-literal element so it is flagged
    ``dynamic`` rather than guessed.
    """
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None, True
    pairs: List[list] = []
    for elt in node.elts:
        if isinstance(elt, (ast.Tuple, ast.List)) and len(elt.elts) == 2:
            kv, kd = _literal_or_none(elt.elts[0])
            vv, vd = _literal_or_none(elt.elts[1])
            if kd or vd:
                return None, True
            pairs.append([kv, vv])
        else:
            return None, True
    return pairs, False


def _field_type_of(value: ast.Call) -> Optional[str]:
    """Return the ``fields.XXX`` type name for a call node, or ``None``."""
    func = value.func
    if isinstance(func, ast.Attribute) and func.attr in FIELD_TYPES:
        return func.attr
    if isinstance(func, ast.Name) and func.id in FIELD_TYPES:
        return func.id
    return None


def _apply_positional(details: Dict[str, Any], first: ast.expr, ftype: str) -> None:
    """Fill comodel / selection / label from positional arg 0 by field type."""
    if ftype in _RELATIONAL_TYPES:
        details["comodel"], _ = _literal_or_none(first)
    elif ftype == "Selection":
        details["selection"], dyn = _literal_selection(first)
        details["dynamic"] = details["dynamic"] or dyn
    else:
        details["label"], dyn = _literal_or_none(first)
        details["dynamic"] = details["dynamic"] or dyn


def _apply_keywords(details: Dict[str, Any], kw: Dict[str, ast.expr]) -> None:
    """Fill content fields from the field call's keyword arguments."""
    if "string" in kw:  # explicit string= overrides positional label
        details["label"], dyn = _literal_or_none(kw["string"])
        details["dynamic"] = details["dynamic"] or dyn

    if "comodel_name" in kw:
        details["comodel"], _ = _literal_or_none(kw["comodel_name"])

    for key in ("help", "inverse_name", "relation", "compute", "related"):
        if key in kw:
            details[key], dyn = _literal_or_none(kw[key])
            details["dynamic"] = details["dynamic"] or (dyn and key in _DYNAMIC_SENSITIVE)

    for key in ("required", "readonly", "store"):
        if key in kw:
            val, _ = _literal_or_none(kw[key])
            details[key] = val if isinstance(val, bool) else None

    if "default" in kw:
        node = kw["default"]
        inner = _translation_wrapped(node)
        target = inner if inner is not None else node
        if isinstance(target, ast.Constant):
            details["default"] = _unparse(target) or repr(target.value)
        else:
            details["dynamic"] = True  # non-literal default (lambda, callable, …)

    if "selection" in kw:
        details["selection"], dyn = _literal_selection(kw["selection"])
        details["dynamic"] = details["dynamic"] or dyn


def extract_field_details(stmt: ast.stmt) -> Optional[Dict[str, Any]]:
    """Return the full content picture for a ``fields.XXX(...)`` assignment.

    Args:
        stmt: An AST statement node to inspect.

    Returns:
        A dict with ``type``, ``label``, ``help``, ``required``, ``readonly``,
        ``store``, ``comodel``, ``inverse_name``, ``relation``, ``compute``,
        ``related``, ``default``, ``selection`` and ``dynamic`` — or ``None``
        when the statement is not a field assignment. Non-literal values stay
        ``None`` and set ``dynamic=True`` (spec §8.4). Never evaluates.
    """
    if not isinstance(stmt, ast.Assign):
        return None
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return None
    value = stmt.value
    if not isinstance(value, ast.Call):
        return None
    ftype = _field_type_of(value)
    if ftype is None:
        return None

    details: Dict[str, Any] = {
        "type": ftype,
        "label": None,
        "help": None,
        "required": None,
        "readonly": None,
        "store": None,
        "comodel": None,
        "inverse_name": None,
        "relation": None,
        "compute": None,
        "related": None,
        "default": None,
        "selection": None,
        "dynamic": False,
    }

    if value.args:
        _apply_positional(details, value.args[0], ftype)
    _apply_keywords(details, {k.arg: k.value for k in value.keywords if k.arg is not None})

    return details


def reconstruct_signature(fn: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> Optional[str]:
    """Return the parenthesized param list, e.g. ``'(self, a, b=2, *args, **kwargs)'``.

    Reconstructed from the AST via ``ast.unparse`` (defaults rendered as their
    source repr). Returns ``None`` when ``ast.unparse`` is unavailable (py<3.9).
    """
    rendered = _unparse(fn.args)
    return f"({rendered})" if rendered is not None else None


def decorator_call_texts(fn: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> List[str]:
    """Return the full decorator source texts, e.g. ``["api.depends('a.b', 'c')"]``.

    Uses ``ast.unparse``; decorators that fail to unparse (or py<3.9) are
    skipped, yielding an empty list rather than raising.
    """
    out: List[str] = []
    for dec in fn.decorator_list:
        text = _unparse(dec)
        if text is not None:
            out.append(text)
    return out


def _get_decorator_names(func_node: ast.FunctionDef) -> List[str]:
    """Return all decorator name strings from a function definition."""
    names = []
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(dec.attr)
            names.append(f"{getattr(dec.value, 'id', '')}.{dec.attr}")
        elif isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Attribute):
                names.append(func.attr)
            elif isinstance(func, ast.Name):
                names.append(func.id)
    return names


def classify_method(
    name: str,
    decorator_names: List[str],
    referencing_kwargs: Iterable[str] = (),
) -> str:
    """Decide a method's section.

    Args:
        name: Method name.
        decorator_names: Flat list of decorator name strings (see
            ``_get_decorator_names``).
        referencing_kwargs: Field kwargs that reference this method on the same
            model (across all classes/files/modules available at classification
            time), e.g. ``{"compute", "inverse"}``.

    Returns:
        One of the ``METHOD_SECTION_*`` constants (first matching rule wins).

    Priority (first match wins):
      1. CRUD name.
      2. Standard default-provider name (default_get) → DEFAULT METHODS.
      3. @api.depends → COMPUTE METHODS.
      4. @api.onchange → ONCHANGE METHODS.
      5. @api.constrains → CONSTRAINT METHODS.
      6. Referenced by a field via compute=/inverse=/search= → COMPUTE METHODS.
      7. Referenced by a field via default= → DEFAULT METHODS.
      8. Referenced by a field via selection= → SELECTION METHODS.
      9. action_ or button_ prefix → ACTION METHODS.
     10. _ prefix → HELPER METHODS.
     11. Default → BUSINESS METHODS.

    `@api.model` is intentionally NOT a classification signal. It only marks that
    the method receives the model class rather than a recordset as `self`; this
    orthogonal property appears across all sections. Treating it as a signal would
    misclassify or produce a new meaningless section.

    `SELECTION METHODS` is ONLY reachable via the `referencing_kwargs` path
    (`"selection"` in the set). There is no Odoo decorator for selection methods
    and no established naming convention — `selection=` on a field declaration is
    the sole detection signal.

    See docs/reference/method-classification.md for the full rationale behind
    each rule and guidance on extending the system.
    """
    if name in CRUD_NAMES:
        return METHOD_SECTION_CRUD
    if name in DEFAULT_NAMES:
        return METHOD_SECTION_DEFAULT
    if any(d in ("api.depends", "depends") for d in decorator_names):
        return METHOD_SECTION_COMPUTE
    if any(d in ("api.onchange", "onchange") for d in decorator_names):
        return METHOD_SECTION_ONCHANGE
    if any(d in ("api.constrains", "constrains") for d in decorator_names):
        return METHOD_SECTION_CONSTRAINT
    refs = set(referencing_kwargs)
    if refs & {"compute", "inverse", "search"}:
        return METHOD_SECTION_COMPUTE
    if "default" in refs:
        return METHOD_SECTION_DEFAULT
    if "selection" in refs:
        return METHOD_SECTION_SELECTION
    if name.startswith(("action_", "button_")):
        return METHOD_SECTION_ACTION
    if name.startswith("_"):
        return METHOD_SECTION_HELPER
    return METHOD_SECTION_BUSINESS


def build_module_field_refs(
    py_files: List[Path],
) -> Dict[Tuple[str, str], List[str]]:
    """Build a {(model, method_name): [kwarg, ...]} index from a list of model files.

    Used by the refactor CLI to pre-compute cross-file field→method links within
    a single module before running per-file analysis.

    Args:
        py_files: Python source files from a single Odoo module to index.

    Returns:
        Mapping of ``(model_name, method_name)`` to the list of field kwargs
        that reference the method (e.g. ``["compute", "inverse"]``).
    """
    refs: Dict[Tuple[str, str], List[str]] = {}
    for py_file in py_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not is_odoo_model_class(node):
                continue
            _name, _inherit = get_model_names(node)
            for model_name in [_name] if _name else _inherit:
                for stmt in node.body:
                    if not isinstance(stmt, ast.Assign):
                        continue
                    for kwarg, target in extract_field_refs(stmt).items():
                        key = (model_name, target)
                        refs.setdefault(key, []).append(kwarg)
    return refs


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
#           "source_end_line": int,  # last source line of the definition (degrades to source_line on py3.7)
#           "field_type":  str | None,  # set when kind == 'field'; e.g. 'Boolean'
#           "section":     str | None,  # set when kind == 'method'; canonical section name
#       },
#       ...
#   ],
#   "field_refs": [
#       {
#           "model":         str,
#           "field_name":    str,
#           "module":        str,
#           "kwarg":         str,   # 'compute' | 'inverse' | 'search' | 'default' | 'selection'
#           "target_method": str,
#       },
#       ...
#   ],
#   "model_origins": [
#       {
#           "model":         str,   # model name being acted upon
#           "module":        str,
#           "origin":        str,
#           "role":          str,   # 'create' | 'extend' | 'prototype' (prototype set in build.py)
#           "model_type":    str,   # 'model' | 'transient' | 'abstract'
#           "inherit_json":  str,   # JSON array of _inherit values (for prototype detection)
#           "inherits_json": str,   # JSON object of _inherits dict
#           "source_file":   str,
#           "source_line":   int,
#       },
#       ...
#   ],
# }


def scan_module(  # noqa: C901
    module_dir: Path,
    origin: str,
    tier_root: Path,
) -> Dict[str, Any]:
    """Scan a single Odoo module directory.

    Args:
        module_dir: absolute path to the module (must contain __manifest__.py).
        origin:     tier label ('odoo', 'enterprise', 'third-party', 'apik').
        tier_root:  root used to compute relative source_file paths.

    Returns:
        A ScanResult dict with keys 'modules', 'symbols', and 'field_refs'.
    """
    module_name = module_dir.name
    result: Dict[str, Any] = {"modules": {}, "symbols": [], "field_refs": [], "model_origins": []}

    # --- manifest ---
    depends = load_manifest(module_dir).get("depends", [])
    result["modules"][module_name] = {"origin": origin, "depends": depends}

    # --- models ---
    models_dir = module_dir / "models"
    if not models_dir.is_dir():
        return result

    # Parse all model files up front so we can do two passes.
    parsed_files: List[Tuple[Path, str, ast.Module]] = []
    for py_file in models_dir.rglob("*.py"):
        tree = _parse_file(py_file)
        if tree is None:
            continue
        try:
            rel_path = str(py_file.relative_to(tier_root))
        except ValueError:
            rel_path = str(py_file)
        parsed_files.append((py_file, rel_path, tree))

    # ---- Pass 1: collect field symbols and field_refs across the whole module. ----
    # Keyed by (model, target_method) → list of kwargs
    refs_by_target: Dict[Tuple[str, str], List[str]] = {}
    field_symbols: List[Dict[str, Any]] = []
    pending_methods: List[Tuple[str, str, ast.FunctionDef, str, int, int]] = []

    for _, rel_path, tree in parsed_files:
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not is_odoo_model_class(node):
                continue

            _name, _inherit = get_model_names(node)
            _inherits_dict = get_inherits(node)
            model_type = get_model_type(node)
            _description = get_description(node)

            if _name is not None:
                role = "extend" if _name in _inherit else "create"
                result["model_origins"].append(
                    {
                        "model": _name,
                        "module": module_name,
                        "origin": origin,
                        "role": role,
                        "model_type": model_type,
                        "inherit_json": json.dumps(_inherit),
                        "inherits_json": json.dumps(_inherits_dict),
                        "source_file": rel_path,
                        "source_line": node.lineno,
                        "description": _description,
                    }
                )
            else:
                for inh in _inherit:
                    result["model_origins"].append(
                        {
                            "model": inh,
                            "module": module_name,
                            "origin": origin,
                            "role": "extend",
                            "model_type": model_type,
                            "inherit_json": json.dumps([]),
                            "inherits_json": json.dumps({}),
                            "source_file": rel_path,
                            "source_line": node.lineno,
                            "description": _description,
                        }
                    )

            target_models: List[str] = [_name] if _name else _inherit

            for model_name in target_models:
                for stmt in node.body:
                    fld = is_field_assignment(stmt)
                    if fld:
                        fname, lineno, ftype = fld
                        end_lineno = getattr(stmt, "end_lineno", None) or lineno
                        field_symbols.append(
                            {
                                "model": model_name,
                                "name": fname,
                                "kind": "field",
                                "origin": origin,
                                "module": module_name,
                                "source_file": rel_path,
                                "source_line": lineno,
                                "source_end_line": end_lineno,
                                "field_type": ftype,
                                "section": None,
                            }
                        )
                        for kwarg, target in extract_field_refs(stmt).items():
                            refs_by_target.setdefault((model_name, target), []).append(kwarg)
                            result["field_refs"].append(
                                {
                                    "model": model_name,
                                    "field_name": fname,
                                    "module": module_name,
                                    "kwarg": kwarg,
                                    "target_method": target,
                                }
                            )
                        continue
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        pending_methods.append(
                            (
                                model_name,
                                rel_path,
                                stmt,
                                stmt.name,
                                stmt.lineno,
                                getattr(stmt, "end_lineno", None) or stmt.lineno,
                            )
                        )

    # ---- Pass 2: classify methods using the collected field refs. ----
    method_symbols: List[Dict[str, Any]] = []
    for model_name, rel_path, fn_node, mname, lineno, end_lineno in pending_methods:
        ref_kwargs = refs_by_target.get((model_name, mname), [])
        decs = _get_decorator_names(fn_node)
        section = classify_method(mname, decs, ref_kwargs)
        method_symbols.append(
            {
                "model": model_name,
                "name": mname,
                "kind": "method",
                "origin": origin,
                "module": module_name,
                "source_file": rel_path,
                "source_line": lineno,
                "source_end_line": end_lineno,
                "field_type": None,
                "section": section,
            }
        )

    result["symbols"] = field_symbols + method_symbols
    return result


def scan_tier(
    tier_root: Path,
    origin: str,
    allowed_modules: Optional[Set[str]] = None,
) -> Result[Dict[str, Any]]:
    """Scan all addon modules under tier_root.

    Args:
        tier_root:       directory whose immediate children are Odoo modules.
        origin:          tier label.
        allowed_modules: if set, only modules whose name is in this set are scanned.

    Returns:
        Merged ScanResult for all scanned modules.
    """
    merged: Dict[str, Any] = {"modules": {}, "symbols": [], "field_refs": [], "model_origins": []}
    result: "Result[Dict[str, Any]]" = Result()

    if not tier_root.is_dir():
        result.add_warning(f"Tier root not found, skipping: {tier_root}")
        result.data = merged
        return result

    count = 0
    for entry in sorted(tier_root.iterdir()):
        if not entry.is_dir():
            continue
        if allowed_modules and entry.name not in allowed_modules:
            continue
        if not load_manifest(entry):
            continue

        data = scan_module(entry, origin, tier_root)
        merged["modules"].update(data["modules"])
        merged["symbols"].extend(data["symbols"])
        merged["field_refs"].extend(data.get("field_refs", []))
        merged["model_origins"].extend(data.get("model_origins", []))
        count += 1

    result.add_message(f"[{origin}] {tier_root} → {count} modules")
    result.data = merged
    return result


def odoo_addons_roots(odoo_path: Path) -> List[Path]:
    """Return the standard addons roots inside an Odoo community tree.

    Odoo community keeps modules in two places:

    - ``<root>/addons/``        standard modules (sale, account…)
    - ``<root>/odoo/addons/``   core modules (base, web, mail…)

    Args:
        odoo_path: Path to the root of an Odoo community checkout.

    Returns:
        List of existing addons root paths. Falls back to ``[odoo_path]``
        if neither standard subdirectory exists.
    """
    candidates = [odoo_path / "addons", odoo_path / "odoo" / "addons"]
    roots = [p for p in candidates if p.is_dir()]
    if not roots:
        # log.warning("No addons/ or odoo/addons/ found under %s — falling back to root.", odoo_path)
        roots = [odoo_path]
    return roots


def discover_root_addons(
    repo_path: Path,
    allowed_modules: Optional[Set[str]] = None,
) -> Dict[str, List[Tuple[str, Path]]]:
    """Walk repo_path for root-level Odoo addons and group them by tier.

    # TODO: Must be replace by `io/file.py:find_addons` by extending the logic if needed

    Three tiers are recognised:
        - 'third-party': symlink whose real path contains '/.third-party/'.
        - 'apik':        symlink whose real path contains '/apik-addons/'.
        - 'local':       real directory at the repo root with a manifest.

    Symlinks that resolve outside the known submodule tiers are logged and
    skipped.

    Returns:
        { origin: [(module_name, real_module_path), ...] }
    """
    markers = _tier_markers()
    tiers: Dict[str, List[Tuple[str, Path]]] = {origin: [] for origin in markers}
    tiers["local"] = []

    # Search at depth 1 under repo_path and its immediate non-hidden children.
    candidates: List[Path] = [repo_path]
    for child in repo_path.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            candidates.append(child)

    seen_real: Set[Path] = set()

    for search_dir in candidates:
        if not search_dir.is_dir():
            continue
        try:
            entries = list(search_dir.iterdir())
        except PermissionError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            module_name = entry.name
            if allowed_modules and module_name not in allowed_modules:
                continue
            real = entry.resolve()
            if real in seen_real:
                continue

            if entry.is_symlink():
                seen_real.add(real)
                real_str = str(real)
                matched = False
                for origin, marker in markers.items():
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
                continue

            # Non-symlink real directory: only counts as 'local' if it has a
            # manifest AND it sits directly under the repo root. We deliberately
            # do not descend into nested real directories.
            if search_dir != repo_path:
                continue
            if not (entry / "__manifest__.py").exists() and not (entry / "__openerp__.py").exists():
                continue
            seen_real.add(real)
            tiers["local"].append((module_name, real))

    return tiers


def tier_root_from_real_path(origin: str, real_path: Path) -> Optional[Path]:
    """Derive the tier root directory from a module's real path.

    Args:
        origin: Tier name (e.g. ``'third-party'`` or ``'apik'``).
        real_path: Resolved (non-symlink) path of the module directory.

    Returns:
        The tier root path, or ``None`` if the marker is not found in the path.

        e.g. ``/repo/.third-party/sale-workflow/sale_order_type``
             → ``/repo/.third-party``
    """
    marker = _tier_markers().get(origin)
    if not marker:
        return None
    real_str = str(real_path)
    idx = real_str.find(marker)
    if idx == -1:
        return None
    return Path(real_str[: idx + len(marker) - 1])
