# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: refactor.py — oops/io/refactor.py

"""CST/AST helpers and rewriter for Odoo model files.

Reads model files, classifies fields and methods against a project KB, and
rewrites class bodies to apply canonical section headers and Google-style
docstring skeletons. Pure file-I/O — no git, no CLI."""

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import libcst as cst
from oops.kb.resolve import (
    format_source_line,
    resolve_symbol,
)
from oops.kb.scanner import (
    FIELD_TYPES,
    METHOD_SECTION_ACTION,
    METHOD_SECTION_BUSINESS,
    METHOD_SECTION_COMPUTE,
    METHOD_SECTION_CONSTRAINT,
    METHOD_SECTION_CRUD,
    METHOD_SECTION_DEFAULT,
    METHOD_SECTION_HELPER,
    METHOD_SECTION_ONCHANGE,
    METHOD_SECTION_SELECTION,
    _get_decorator_names,
    classify_method,
    extract_field_refs,
    get_model_names,
    is_field_assignment,
    is_odoo_model_class,
)
from oops.kb.store import KBReader
from oops.utils.compat import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METHOD_SECTIONS = [
    "CONSTRAINTS",
    METHOD_SECTION_COMPUTE,
    METHOD_SECTION_SELECTION,
    METHOD_SECTION_DEFAULT,
    METHOD_SECTION_ONCHANGE,
    METHOD_SECTION_CONSTRAINT,
    METHOD_SECTION_CRUD,
    METHOD_SECTION_HELPER,
    METHOD_SECTION_ACTION,
    METHOD_SECTION_BUSINESS,
]


def _make_header(name: str) -> str:
    return f"# === {name} === #"


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
    has_docstring: bool = False
    has_super: bool = False
    super_methods: List[str] = field(default_factory=lambda: [])
    kb_entry: Optional[Dict[str, Any]] = None
    is_override: bool = False
    field_type: Optional[str] = None


@dataclass
class ClassInfo:
    """Information about an Odoo model class found in a source file.

    Attributes:
        class_name: Python class name.
        model_name: Value of ``_name``, or ``None`` when only ``_inherit`` is set.
        inherit: Values of ``_inherit`` (may be empty).
        is_new_model: True when the class introduces a new model (has ``_name``).
        lineno: Source line number of the class definition.
        symbols: Ordered list of fields and methods in the class.
    """

    class_name: str
    model_name: Optional[str]
    inherit: List[str]
    is_new_model: bool
    lineno: int
    symbols: List[SymbolInfo] = field(default_factory=lambda: [])

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
        logging.getLogger(__name__).warning("Syntax error in %s: %s", py_file, exc)
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
        is_new_model = not kb.model_exists(model_name)
        has_class_doc = _has_class_docstring(node)

        ci = ClassInfo(
            class_name=node.name,
            model_name=_name,
            inherit=_inherit,
            is_new_model=is_new_model,
            lineno=node.lineno,
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
                if ci.is_inherit or not is_new_model:
                    section = "INHERITED FIELDS" if kb_entry else "NEW FIELDS"
                else:
                    section = "BASE FIELDS"
                ci.symbols.append(
                    SymbolInfo(
                        name=fname,
                        kind="field",
                        section=section,
                        lineno=lineno,
                        kb_entry=kb_entry,
                        field_type=ftype,
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

            ci.symbols.append(
                SymbolInfo(
                    name=stmt.name,
                    kind="method",
                    section=section,
                    lineno=stmt.lineno,
                    has_docstring=has_doc,
                    has_super=has_super,
                    super_methods=super_methods,
                    kb_entry=kb_entry,
                    is_override=bool(kb_entry) and not has_super,
                )
            )

        results.append(ci)

    return results


# ---------------------------------------------------------------------------
# Docstring content builders (return list of lines, no quotes)
# ---------------------------------------------------------------------------


def _method_docstring_lines(sym: SymbolInfo) -> List[str]:
    """Return the inner lines of a method docstring (no triple quotes)."""
    if sym.kb_entry:
        src = format_source_line(sym.kb_entry)
        upstream_section = sym.kb_entry.get("section")
        mod_method = f"{sym.kb_entry.get('module', '?')}.{sym.name}"
        section_hint = f" [{upstream_section}]" if upstream_section else ""
        if sym.is_override:
            return [
                "",
                f"Override {mod_method}{section_hint} — upstream implementation is NOT called.",
                "",
                f"Source: {src}",
                "",
                "Args:",
                "    # TODO: document args if any beyond implicit self.",
                "",
                "Returns:",
                "    # TODO: document return value.",
                "",
                "Warning:",
                "    This method fully replaces the upstream behaviour.",
                "    # TODO: explain why super() is intentionally not called.",
                "",
            ]
        else:
            return [
                "",
                f"Inherit {mod_method}{section_hint}.",
                "",
                f"Source: {src}",
                "",
                "Args:",
                "    # TODO: document args if any beyond implicit self.",
                "",
                "Returns:",
                "    # TODO: document return value.",
                "",
                "Note:",
                "    # TODO: describe what this method adds vs. the upstream implementation.",
                "",
            ]
    else:
        return [
            "",
            f"{sym.name}.",
            "",
            "Args:",
            "    # TODO: document args if any beyond implicit self.",
            "",
            "Returns:",
            "    # TODO: document return value.",
            "",
            "Note:",
            "    # TODO: describe the business logic.",
            "",
        ]


def _class_docstring_lines(ci: ClassInfo) -> List[str]:
    model = ci.model_name or "unknown.model"
    return [
        "",
        f"Custom model: {model}.",
        "",
        "# TODO: describe the purpose of this model, its business context,",
        "# and its relationship to other models in the system.",
        "",
    ]


# ---------------------------------------------------------------------------
# CST node builders
# ---------------------------------------------------------------------------


def _build_docstring_stmt(
    lines: List[str],
    indent_spaces: int = 8,
) -> cst.SimpleStatementLine:
    """Build a CST statement for a triple-quoted docstring.

    `lines` is the list of content lines (without triple-quote delimiters).
    `indent_spaces` is the indentation of the method body.
    """
    pad = " " * indent_spaces
    # Join content with newline + padding
    inner = ("\n" + pad).join(lines)
    raw_str = f'"""{inner}"""'
    try:
        expr = cst.parse_expression(raw_str)
    except cst.ParserSyntaxError:
        # Absolute fallback: single-line docstring
        first = next((ln for ln in lines if ln.strip()), "TODO")
        expr = cst.parse_expression(f'"""{first.strip()}"""')
    return cst.SimpleStatementLine(body=[cst.Expr(value=expr)])


def _build_header_leading_line(section_name: str) -> List[cst.EmptyLine]:
    """Return EmptyLines to attach as leading_lines to the first stmt of a section."""
    return [
        cst.EmptyLine(),  # blank line before header
        cst.EmptyLine(comment=cst.Comment(value=_make_header(section_name))),
    ]


# ---------------------------------------------------------------------------
# libcst rewriter
# ---------------------------------------------------------------------------


class _ModelRewriter(cst.CSTTransformer):
    def __init__(self, classes: List[ClassInfo]) -> None:
        self._classes = {ci.class_name: ci for ci in classes}
        self._log = logging.getLogger(__name__)

    def leave_ClassDef(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        ci = self._classes.get(updated_node.name.value)
        if ci is None:
            return updated_node
        new_body = self._rewrite_body(updated_node.body, ci)
        return updated_node.with_changes(body=new_body)

    def _rewrite_body(
        self,
        body: cst.IndentedBlock,
        ci: ClassInfo,
    ) -> cst.IndentedBlock:
        stmts = list(body.body)

        # Determine body indent (default 4 for class body, 8 for method body).
        body_indent = len(body.indent) if isinstance(body.indent, str) else 4
        method_body_indent = body_indent + 4

        # Sort symbols by lineno for cursor-based matching.
        field_syms = sorted([s for s in ci.symbols if s.kind == "field"], key=lambda x: x.lineno)
        method_syms = sorted([s for s in ci.symbols if s.kind == "method"], key=lambda x: x.lineno)
        field_cursor = 0
        method_cursor = 0

        # Buckets.
        private_attrs: List[cst.BaseStatement] = []
        field_buckets: Dict[str, List[cst.BaseStatement]] = {
            "INHERITED FIELDS": [],
            "NEW FIELDS": [],
            "BASE FIELDS": [],
        }
        method_buckets: Dict[str, List[cst.BaseStatement]] = {s: [] for s in METHOD_SECTIONS}
        unclassified: List[cst.BaseStatement] = []

        for stmt in stmts:
            # Strip ALL leading_lines (including any section headers embedded there)
            # so headers are re-attached cleanly by _append_section.
            # We never skip a statement just because it has a header in leading_lines —
            # after stripping, it will be classified normally.
            stmt = _strip_leading_lines(stmt)

            # Existing class docstring: keep as-is at front.
            if _is_class_docstring(stmt):
                private_attrs.insert(0, stmt)  # will be prepended before _name etc.
                continue

            # Private underscore attributes (_name, _inherit, …).
            if _is_private_attr_stmt(stmt):
                private_attrs.append(stmt)
                continue

            # Field assignment.
            if _is_field_stmt_cst(stmt):
                if field_cursor < len(field_syms):
                    sym = field_syms[field_cursor]
                    field_cursor += 1
                    field_buckets[sym.section].append(stmt)
                else:
                    unclassified.append(stmt)
                continue

            # Method / function.
            if isinstance(stmt, cst.FunctionDef):
                if method_cursor < len(method_syms):
                    sym = method_syms[method_cursor]
                    method_cursor += 1
                    stmt = self._inject_docstring(stmt, sym, method_body_indent)
                    method_buckets[sym.section].append(stmt)
                else:
                    unclassified.append(stmt)
                continue

            unclassified.append(stmt)

        # Class docstring for new models (if not already present).
        class_doc_stmts: List[cst.BaseStatement] = []
        if getattr(ci, "_needs_class_docstring", False):
            doc_stmt = _build_docstring_stmt(_class_docstring_lines(ci), indent_spaces=body_indent)
            class_doc_stmts.append(doc_stmt)

        # Reassemble.
        new_stmts: List[cst.BaseStatement] = []

        # 1. Class docstring (new models) then private attrs.
        new_stmts.extend(class_doc_stmts)
        new_stmts.extend(private_attrs)

        # 2. Fields.
        if ci.is_inherit or not ci.is_new_model:
            _append_section("INHERITED FIELDS", field_buckets["INHERITED FIELDS"], new_stmts)
            _append_section("NEW FIELDS", field_buckets["NEW FIELDS"], new_stmts)
        else:
            _append_section("BASE FIELDS", field_buckets["BASE FIELDS"], new_stmts)

        # 3. Methods.
        for sec in METHOD_SECTIONS:
            _append_section(sec, method_buckets[sec], new_stmts)

        # 4. Unclassified.
        new_stmts.extend(unclassified)

        if not new_stmts:
            return body

        return body.with_changes(body=new_stmts)

    def _inject_docstring(
        self,
        func_node: cst.FunctionDef,
        sym: SymbolInfo,
        indent_spaces: int,
    ) -> cst.FunctionDef:
        if sym.has_docstring:
            return func_node
        doc_stmt = _build_docstring_stmt(_method_docstring_lines(sym), indent_spaces=indent_spaces)
        body_stmts = list(func_node.body.body)
        return func_node.with_changes(body=func_node.body.with_changes(body=[doc_stmt, *body_stmts]))


# ---------------------------------------------------------------------------
# Section assembly helper
# ---------------------------------------------------------------------------


def _append_section(
    name: str,
    items: List[cst.BaseStatement],
    target: List[cst.BaseStatement],
) -> None:
    """Append items to target, adding a header on the first item's leading_lines."""
    if not items:
        return
    header_lines = _build_header_leading_line(name)
    first = items[0]
    existing = list(getattr(first, "leading_lines", []))
    # Strip existing blank lines to avoid double-blank.
    stripped = [ln for ln in existing if ln.comment is not None]
    new_leading = header_lines + stripped
    try:
        first = first.with_changes(leading_lines=new_leading)
        items = [first] + items[1:]
    except Exception:
        pass  # If with_changes fails, use the item as-is
    target.extend(items)


# ---------------------------------------------------------------------------
# CST utility helpers
# ---------------------------------------------------------------------------


def _strip_leading_lines(stmt: cst.BaseStatement) -> cst.BaseStatement:
    """Remove all leading_lines from a statement (comments and blank lines).

    This ensures that when statements are reassembled into sections, they
    don't carry over stale comments or spurious blank lines from the original
    source. Headers and spacing are re-applied by _append_section.
    """
    try:
        return stmt.with_changes(leading_lines=[])
    except Exception:
        return stmt


# ---------------------------------------------------------------------------
# CST predicate helpers
# ---------------------------------------------------------------------------


def _is_class_docstring(stmt: cst.BaseStatement) -> bool:
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    for small in stmt.body:
        if isinstance(small, cst.Expr):
            v = small.value
            if isinstance(v, (cst.SimpleString, cst.ConcatenatedString, cst.FormattedString)):
                return True
    return False


def _is_private_attr_stmt(stmt: cst.BaseStatement) -> bool:
    """Return True for _name, _inherit, _description, etc. assignments."""
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    for small in stmt.body:
        if isinstance(small, cst.Assign):
            for t in small.targets:
                if isinstance(t.target, cst.Name) and t.target.value.startswith("_"):
                    return True
        elif isinstance(small, cst.AnnAssign):
            if isinstance(small.target, cst.Name) and small.target.value.startswith("_"):
                return True
    return False


def _is_field_stmt_cst(stmt: cst.BaseStatement) -> bool:
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    for small in stmt.body:
        if isinstance(small, cst.Assign):
            val = small.value
            if isinstance(val, cst.Call):
                func = val.func
                if isinstance(func, cst.Attribute) and func.attr.value in FIELD_TYPES:
                    return True
                if isinstance(func, cst.Name) and func.value in FIELD_TYPES:
                    return True
    return False


# ---------------------------------------------------------------------------
# File rewrite
# ---------------------------------------------------------------------------


def rewrite_file(py_file: Path, classes: List[ClassInfo]) -> str:
    """Rewrite a Python source file by injecting section headers and docstring skeletons.

    Uses ``libcst`` for AST-preserving rewriting so comments and formatting are
    retained. Returns the original source unchanged when ``classes`` is empty or
    the file fails to parse.

    Args:
        py_file: Path to the Python source file to rewrite.
        classes: Analysis result from ``analyse_file``; drives which rewrites
            are applied.

    Returns:
        Rewritten source code as a string, or the original source on failure.
    """
    source = py_file.read_text(encoding="utf-8", errors="replace")
    if not classes:
        return source
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        logging.getLogger(__name__).error("Cannot parse %s: %s", py_file, exc)
        return source
    new_tree = tree.visit(_ModelRewriter(classes))
    return new_tree.code
