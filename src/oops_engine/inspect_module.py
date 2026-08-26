# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: inspect_module.py — oops_engine/inspect_module.py

"""Per-file AST inspection of Odoo model files.

Reads model files and classifies fields and methods against a project KB.
Pure, read-only analysis — no git, no CLI, no source rewriting (see
``oops.io.refactor`` for the rewrite/mutation half that consumes this)."""

import ast
from dataclasses import dataclass, field
from pathlib import Path

import libcst as cst
from oops.core.compat import Any, Dict, List, Optional, Tuple, Union
from oops.core.logger import log
from oops_engine.resolve import resolve_symbol, resolve_symbol_root
from oops_engine.scanner import (
    _extract_string_value,
    _get_decorator_names,
    classify_method,
    decorator_call_texts,
    extract_field_details,
    extract_field_refs,
    get_model_names,
    get_model_type,
    is_field_assignment,
    is_odoo_model_class,
    reconstruct_signature,
)
from oops_engine.store import KBReader

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SymbolInfo:
    """Information about a single field or method within an Odoo model class.

    Attributes:
        name: Symbol name.
        kind: ``'field'`` or ``'method'``.
        section: Canonical section header (e.g. ``'COMPUTE METHODS'``).
        lineno: Source line number of the definition.
        end_lineno: Last source line of the definition (0 → unknown).
        has_docstring: True if the method already has a docstring.
        has_super: True if the method calls ``super()``.
        super_methods: Names of methods called via ``super().<name>()``.
        kb_entry: Matching KB record, or ``None`` if not found.
        is_override: True when the symbol is in the KB but has no ``super()`` call.
        field_type: ``fields.XXX`` type string; only set when ``kind == 'field'``.
    """

    name: str
    kind: str
    section: str
    lineno: int
    end_lineno: int = 0
    has_docstring: bool = False
    has_super: bool = False
    super_methods: List[str] = field(default_factory=lambda: [])
    kb_entry: Optional[Dict[str, Any]] = None
    kb_root_entry: Optional[Dict[str, Any]] = None
    is_override: bool = False
    field_type: Optional[str] = None
    # IR v2 content (additive; defaults preserve rewriter behaviour) ----------
    docstring: Optional[str] = None
    """Method docstring text (``ast.get_docstring``); ``None`` when absent."""
    signature: Optional[str] = None
    """Reconstructed method param list, e.g. ``'(self, vals)'``; method-only."""
    decorators: List[str] = field(default_factory=lambda: [])
    """Decorator source texts, e.g. ``["api.depends('a.b')"]``; method-only."""
    field_details: Optional[Dict[str, Any]] = None
    """Output of ``extract_field_details`` (labels/help/kwargs); field-only."""


@dataclass
class ClassInfo:
    """Information about an Odoo model class found in a source file.

    Attributes:
        class_name: Python class name.
        model_name: Value of ``_name``, or ``None`` when only ``_inherit`` is set.
        inherit: Values of ``_inherit`` (may be empty).
        is_new_model: True when this module is the creator of the model, per the KB model_origins table.
        lineno: Source line number of the class definition.
        symbols: Ordered list of fields and methods in the class.
    """

    class_name: str
    model_name: Optional[str]
    inherit: List[str]
    is_new_model: bool
    """True when this class is the creator of the model, as determined by the KB model_origins table."""
    lineno: int
    model_type: str = "model"
    """One of 'model', 'transient', 'abstract'."""
    symbols: List[SymbolInfo] = field(default_factory=lambda: [])
    description: Optional[str] = None
    """Odoo model ``_description`` literal; ``None`` when absent (IR v2)."""
    docstring: Optional[str] = None
    """Python class docstring (``ast.get_docstring``); ``None`` when absent (IR v2)."""
    source_file: Optional[str] = None
    """Module-relative source path of the file holding this class (IR v2)."""

    @property
    def is_inherit(self) -> bool:
        """Return True if this class only extends existing models via ``_inherit``."""
        return bool(self.inherit)


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------


def _has_docstring(func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
    if func_node.body:
        first = func_node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            return isinstance(first.value.value, str)
    return False


def _extract_description(class_node: ast.ClassDef) -> Optional[str]:
    """Return the ``_description = "..."`` string literal, or ``None`` (IR v2)."""
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_description" for t in stmt.targets
        ):
            return _extract_string_value(stmt.value)
    return None


def _has_class_docstring(class_node: ast.ClassDef) -> bool:
    for stmt in class_node.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            return isinstance(stmt.value.value, str)
        if isinstance(stmt, ast.Pass):
            continue
        break
    return False


# ---------------------------------------------------------------------------
# libcst super() detection
# ---------------------------------------------------------------------------


class _SuperDetector(cst.CSTVisitor):
    def __init__(self) -> None:
        self.has_super = False
        self.super_methods: List[str] = []

    def visit_Call(self, node: cst.Call) -> None:
        if (
            isinstance(node.func, cst.Attribute)
            and isinstance(node.func.value, cst.Call)
            and isinstance(node.func.value.func, cst.Name)
            and node.func.value.func.value == "super"
        ):
            self.has_super = True
            self.super_methods.append(node.func.attr.value)


def _detect_super(source: str, func_name: str) -> Tuple[bool, List[str]]:
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return False, []
    for node in tree.body:
        if not isinstance(node, cst.ClassDef):
            continue
        for item in node.body.body:
            if isinstance(item, cst.FunctionDef) and item.name.value == func_name:
                d = _SuperDetector()
                item.visit(d)
                return d.has_super, d.super_methods
    return False, []


# ---------------------------------------------------------------------------
# Analysis entry point
# ---------------------------------------------------------------------------


def analyse_file(
    py_file: Path,
    kb: KBReader,
    modules_index: Dict[str, Any],
    custom_module: str,
    module_local_refs: Optional[Dict[Tuple[str, str], List[str]]] = None,
) -> List[ClassInfo]:
    """Classify every Odoo model class and its symbols in a Python source file.

    Reads the file, parses it with ``ast``, and for each model class found
    resolves its fields and methods against the KB. Syntax errors are logged
    and produce an empty result rather than raising.

    Args:
        py_file: Path to the Python source file to analyse.
        kb: Open KB reader used for symbol and model lookups.
        modules_index: Pre-loaded modules dict from ``KBReader.get_modules()``.
        custom_module: Name of the module being analysed (used for KB lookups).
        module_local_refs: Optional ``{(model, method): [kwarg, ...]}`` index
            of cross-file field→method links within the same module.

    Returns:
        Ordered list of ``ClassInfo`` objects, one per Odoo model class found.
        Empty when the file contains no Odoo model classes or fails to parse.
    """
    source = py_file.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError as exc:
        log.warning("Syntax error in %s: %s", py_file, exc)
        return []

    results: List[ClassInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not is_odoo_model_class(node):
            continue

        _name, _inherit = get_model_names(node)
        target_models = [_name] if _name else _inherit
        if not target_models:
            continue

        model_name = target_models[0]
        # _name absent → pure _inherit class; always an extender regardless of KB.
        # _name in _inherit → Odoo "reopen same model" extension pattern.
        # Only query the KB when _name is set and not self-referential.
        is_new_model = _name is not None and _name not in _inherit and kb.is_model_creator(model_name, custom_module)
        if is_new_model:
            other_creators = [c for c in kb.get_model_creators(model_name) if c["module"] != custom_module]
            if other_creators:
                log.warning(
                    "Model '%s' claimed by multiple creators: %s (also in %s). "
                    "These modules may be mutually exclusive.",
                    model_name,
                    custom_module,
                    [c["module"] for c in other_creators],
                )
        has_class_doc = _has_class_docstring(node)

        ci = ClassInfo(
            class_name=node.name,
            model_name=_name,
            inherit=_inherit,
            is_new_model=is_new_model,
            model_type=get_model_type(node),
            lineno=node.lineno,
            description=_extract_description(node),  # IR v2 model-level content
            docstring=ast.get_docstring(node, clean=True),
        )
        ci._needs_class_docstring = is_new_model and not has_class_doc  # type: ignore[attr-defined]

        # Pass 1: collect field→method refs within this class.
        local_refs: Dict[str, List[str]] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for kwarg, target in extract_field_refs(stmt).items():
                    local_refs.setdefault(target, []).append(kwarg)

        # Pass 2: emit symbols, classifying methods with resolved refs.
        for stmt in node.body:
            fld = is_field_assignment(stmt)
            if fld:
                fname, lineno, ftype = fld
                kb_entries = kb.get_symbol(model_name, fname, "field")
                kb_entry = resolve_symbol(kb_entries, custom_module, modules_index)
                section = "BASE FIELDS" if is_new_model else ("INHERITED FIELDS" if kb_entry else "NEW FIELDS")
                ci.symbols.append(
                    SymbolInfo(
                        name=fname,
                        kind="field",
                        section=section,
                        lineno=lineno,
                        end_lineno=getattr(stmt, "end_lineno", None) or lineno,
                        kb_entry=kb_entry,
                        field_type=ftype,
                        field_details=extract_field_details(stmt),
                    )
                )
                continue

            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            dec_names = _get_decorator_names(stmt)
            # Resolve field→method refs: same-class first, then module-level, then KB.
            if stmt.name in local_refs:
                ref_kwargs = local_refs[stmt.name]
            elif module_local_refs is not None:
                ref_kwargs = module_local_refs.get((model_name, stmt.name), [])
            else:
                ref_kwargs = [k["kwarg"] for k in kb.get_field_refs_for_method(model_name, stmt.name)]
            section = classify_method(stmt.name, dec_names, ref_kwargs)
            has_doc = _has_docstring(stmt)
            has_super, super_methods = _detect_super(source, stmt.name)

            kb_entries = kb.get_symbol(model_name, stmt.name, "method")
            kb_entry = resolve_symbol(kb_entries, custom_module, modules_index)
            kb_root_entry = resolve_symbol_root(kb_entries, custom_module, modules_index)

            ci.symbols.append(
                SymbolInfo(
                    name=stmt.name,
                    kind="method",
                    section=section,
                    lineno=stmt.decorator_list[0].lineno if stmt.decorator_list else stmt.lineno,
                    end_lineno=getattr(stmt, "end_lineno", None) or stmt.lineno,
                    has_docstring=has_doc,
                    has_super=has_super,
                    super_methods=super_methods,
                    kb_entry=kb_entry,
                    kb_root_entry=kb_root_entry,
                    is_override=(not is_new_model) and bool(kb_entry) and not has_super,
                    docstring=ast.get_docstring(stmt, clean=True),
                    signature=reconstruct_signature(stmt),
                    decorators=decorator_call_texts(stmt),
                )
            )

        results.append(ci)

    return results
