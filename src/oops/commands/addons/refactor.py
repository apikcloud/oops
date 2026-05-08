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

import ast
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import libcst as cst
from oops.kb.resolve import (
    format_source_line,
    resolve_symbol,
)
from oops.kb.store import KBReader
from rich.console import Console
from rich.logging import RichHandler

console = Console()

CACHE_DIR_NAME = ".oops-cache"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METHOD_SECTIONS = [
    "CONSTRAINTS",
    "COMPUTE METHODS",
    "SELECTION METHODS",
    "ONCHANGE METHODS",
    "CONSTRAINT METHODS",
    "CRUD METHODS",
    "HELPER METHODS",
    "ACTION METHODS",
    "BUSINESS METHODS",
]

CRUD_NAMES = {"create", "write", "unlink", "copy", "name_search", "_search"}

_FIELD_TYPES = {
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

_ODOO_BASE_CLASSES = {"Model", "TransientModel", "AbstractModel"}

# Regex to detect any existing section header variant.
_HEADER_RE = re.compile(
    r"^\s*#\s*[-=#+*]{2,}\s*([A-Z][A-Z\s]+?)\s*[-=#+*]{0,}\s*(?:#\s*)?$",
    re.IGNORECASE,
)


def _make_header(name: str) -> str:
    return f"# === {name} === #"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SymbolInfo:
    name: str
    kind: str  # 'field' | 'method'
    section: str
    lineno: int
    has_docstring: bool = False
    has_super: bool = False
    super_methods: list[str] = field(default_factory=list)
    kb_entry: dict[str, Any] | None = None
    is_override: bool = False  # in KB but no super()


@dataclass
class ClassInfo:
    class_name: str
    model_name: str | None
    inherit: list[str]
    is_new_model: bool
    lineno: int
    symbols: list[SymbolInfo] = field(default_factory=list)

    @property
    def is_inherit(self) -> bool:
        return bool(self.inherit)


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------


def _is_odoo_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
        if name in _ODOO_BASE_CLASSES:
            return True
    return False


def _get_model_names(node: ast.ClassDef) -> tuple[str | None, list[str]]:
    _name = None
    _inherit: list[str] = []
    for stmt in node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for t in stmt.targets:
            if not isinstance(t, ast.Name):
                continue
            val = stmt.value
            if t.id == "_name":
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    _name = val.value
            elif t.id == "_inherit":
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    _inherit = [val.value]
                elif isinstance(val, ast.List):
                    _inherit = [e.value for e in val.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return _name, _inherit


def _is_field(stmt: ast.stmt) -> tuple[str, int] | None:
    if not isinstance(stmt, ast.Assign):
        return None
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return None
    val = stmt.value
    if isinstance(val, ast.Call):
        func = val.func
        attr = func.attr if isinstance(func, ast.Attribute) else None
        name = func.id if isinstance(func, ast.Name) else None
        if (attr or name) in _FIELD_TYPES:
            return stmt.targets[0].id, stmt.lineno
    return None


def _has_docstring(func_node: ast.FunctionDef) -> bool:
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


def _get_decorator_names(func_node: ast.FunctionDef) -> list[str]:
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


def _classify_method(name: str, decorator_names: list[str]) -> str:
    if name in CRUD_NAMES:
        return "CRUD METHODS"
    if any(d in ("api.depends", "depends") for d in decorator_names):
        return "COMPUTE METHODS"
    if any(d in ("api.onchange", "onchange") for d in decorator_names):
        return "ONCHANGE METHODS"
    if any(d in ("api.constrains", "constrains") for d in decorator_names):
        return "CONSTRAINT METHODS"
    if name.startswith("action_"):
        return "ACTION METHODS"
    if name.startswith("_"):
        return "HELPER METHODS"
    return "BUSINESS METHODS"


# ---------------------------------------------------------------------------
# libcst super() detection
# ---------------------------------------------------------------------------


class _SuperDetector(cst.CSTVisitor):
    def __init__(self) -> None:
        self.has_super = False
        self.super_methods: list[str] = []

    def visit_Call(self, node: cst.Call) -> None:
        if (
            isinstance(node.func, cst.Attribute)
            and isinstance(node.func.value, cst.Call)
            and isinstance(node.func.value.func, cst.Name)
            and node.func.value.func.value == "super"
        ):
            self.has_super = True
            self.super_methods.append(node.func.attr.value)


def _detect_super(source: str, func_name: str) -> tuple[bool, list[str]]:
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
    modules_index: dict[str, Any],
    custom_module: str,
) -> list[ClassInfo]:
    source = py_file.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError as exc:
        logging.getLogger(__name__).warning("Syntax error in %s: %s", py_file, exc)
        return []

    results: list[ClassInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_odoo_class(node):
            continue

        _name, _inherit = _get_model_names(node)
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
        # Store whether class docstring is needed as attribute
        ci._needs_class_docstring = is_new_model and not has_class_doc  # type: ignore[attr-defined]

        for stmt in node.body:
            fld = _is_field(stmt)
            if fld:
                fname, lineno = fld
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
                    )
                )
                continue

            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            dec_names = _get_decorator_names(stmt)
            section = _classify_method(stmt.name, dec_names)
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


def _method_docstring_lines(sym: SymbolInfo) -> list[str]:
    """Return the inner lines of a method docstring (no triple quotes)."""
    if sym.kb_entry:
        src = format_source_line(sym.kb_entry)
        mod_method = f"{sym.kb_entry.get('module', '?')}.{sym.name}"
        if sym.is_override:
            return [
                "",
                f"Override {mod_method} — upstream implementation is NOT called.",
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
                f"Inherit {mod_method}.",
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


def _class_docstring_lines(ci: ClassInfo) -> list[str]:
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
    lines: list[str],
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
        first = next((l for l in lines if l.strip()), "TODO")
        expr = cst.parse_expression(f'"""{first.strip()}"""')
    return cst.SimpleStatementLine(body=[cst.Expr(value=expr)])


def _build_header_leading_line(section_name: str) -> list[cst.EmptyLine]:
    """Return EmptyLines to attach as leading_lines to the first stmt of a section."""
    return [
        cst.EmptyLine(),  # blank line before header
        cst.EmptyLine(comment=cst.Comment(value=_make_header(section_name))),
    ]


# ---------------------------------------------------------------------------
# libcst rewriter
# ---------------------------------------------------------------------------


class _ModelRewriter(cst.CSTTransformer):
    def __init__(self, classes: list[ClassInfo]) -> None:
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
        private_attrs: list[cst.BaseStatement] = []
        field_buckets: dict[str, list[cst.BaseStatement]] = {
            "INHERITED FIELDS": [],
            "NEW FIELDS": [],
            "BASE FIELDS": [],
        }
        method_buckets: dict[str, list[cst.BaseStatement]] = {s: [] for s in METHOD_SECTIONS}
        unclassified: list[cst.BaseStatement] = []

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
        class_doc_stmts: list[cst.BaseStatement] = []
        if getattr(ci, "_needs_class_docstring", False):
            doc_stmt = _build_docstring_stmt(_class_docstring_lines(ci), indent_spaces=body_indent)
            class_doc_stmts.append(doc_stmt)

        # Reassemble.
        new_stmts: list[cst.BaseStatement] = []

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
    items: list[cst.BaseStatement],
    target: list[cst.BaseStatement],
) -> None:
    """Append items to target, adding a header on the first item's leading_lines."""
    if not items:
        return
    header_lines = _build_header_leading_line(name)
    first = items[0]
    existing = list(getattr(first, "leading_lines", []))
    # Strip existing blank lines to avoid double-blank.
    stripped = [l for l in existing if l.comment is not None]
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


def _has_header_in_leading_lines(stmt: cst.BaseStatement) -> bool:
    """Return True if any leading_lines comment looks like a section header."""
    if not hasattr(stmt, "leading_lines"):
        return False
    for line in stmt.leading_lines:
        if line.comment:
            val = line.comment.value  # e.g. "# === COMPUTE METHODS === #"
            # Strip the leading # and check
            inner = val.lstrip("#").strip()
            if re.match(r"^={3,}.*={3,}.*#?\s*$", inner) or re.match(r"^===\s+[A-Z]", val):
                return True
    return False


# ---------------------------------------------------------------------------
# CST predicate helpers
# ---------------------------------------------------------------------------


def _is_section_header_stmt(stmt: cst.BaseStatement) -> bool:
    """Detect a standalone comment line that looks like a section header."""
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    # Check leading_lines for a comment matching our header pattern.
    for line in stmt.leading_lines:
        if line.comment:
            text = line.comment.value  # includes the '#'
            if _HEADER_RE.match(text.lstrip("#").strip() and text or ""):
                return True
    # A line that has ONLY a comment in leading_lines and an empty body (pass)?
    # More reliable: check if the entire line is "# === ... === #"
    # We check the `body` for a trailing comment or the line itself.
    if hasattr(stmt, "trailing_whitespace"):
        tw = stmt.trailing_whitespace
        if tw and tw.comment and _HEADER_RE.match(tw.comment.value):
            return True
    return False


def _comment_line_is_header(comment_val: str) -> bool:
    text = comment_val.lstrip("#").strip()
    return bool(_HEADER_RE.match(comment_val)) or bool(
        re.match(r"^[-=#+*]{2,}\s*[A-Z][A-Z\s]+\s*[-=#+*]{0,}$", text, re.IGNORECASE)
    )


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
                if isinstance(func, cst.Attribute) and func.attr.value in _FIELD_TYPES:
                    return True
                if isinstance(func, cst.Name) and func.value in _FIELD_TYPES:
                    return True
    return False


# ---------------------------------------------------------------------------
# File rewrite
# ---------------------------------------------------------------------------


def rewrite_file(py_file: Path, classes: list[ClassInfo]) -> str:
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


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, markup=True)],
    )


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
    help=("Path to the project KB database. Defaults to auto-detection from nearest .oops-cache directory."),
)
@click.option(
    "--version",
    default="17.0",
    show_default=True,
    help="Odoo version — used to locate the project KB when --kb is not given.",
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
def main(
    module_path: Path,
    kb_path: Path | None,
    version: str,
    branch: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Refactor the Odoo custom module at MODULE_PATH.

    Applies canonical section headers and minimal docstring skeletons to all
    model files, then commits the result on a dedicated git branch.
    """
    _setup_logging(verbose)
    log = logging.getLogger(__name__)

    module_path = module_path.resolve()
    module_name = module_path.name

    # --- Locate KB ---
    if kb_path is None:
        search = module_path
        while search != search.parent:
            candidate = search / CACHE_DIR_NAME / f"kb_project_{version}.db"
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
