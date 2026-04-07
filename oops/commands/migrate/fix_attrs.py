# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: fix_attrs.py — oops/commands/migrate/fix_attrs.py

"""
Convert deprecated attrs= and states= XML attributes to Odoo 17 format.

Walks recursively through XML files in PATH (default: current directory),
finds elements using the legacy attrs= / states= syntax, and rewrites them
to use the modern inline attributes: invisible, readonly, required,
column_invisible.

Before running this command, manually convert any invisible= attributes on
<tree> fields to column_invisible= where appropriate — the script cannot
distinguish cell-level from column-level visibility automatically.

Based on https://github.com/pierrelocus/odoo-attrs-replace
"""

import re
from pathlib import Path

import click

from oops.commands.base import command

# ---------------------------------------------------------------------------
# New attribute names recognised by Odoo 17+
# ---------------------------------------------------------------------------

_NEW_ATTRS = ("invisible", "required", "readonly", "column_invisible")

# ---------------------------------------------------------------------------
# Domain normalisation helpers (ported from odoo/osv/expression.py)
# ---------------------------------------------------------------------------


def _normalize_domain(domain):
    """Add implicit '&' operators so every domain is fully-qualified."""
    if len(domain) == 1:
        return domain
    result = []
    expected = 1
    op_arity = {"!": 1, "&": 2, "|": 2}
    for token in domain:
        if expected == 0:
            result[0:0] = ["&"]
            expected = 1
        if isinstance(token, (list, tuple)):
            expected -= 1
            token = tuple(token)
        else:
            expected += op_arity.get(token, 0) - 1
        result.append(token)
    return result


def _stringify_leaf(leaf):
    """Convert a domain leaf tuple to a Python expression string."""
    stringify = ""
    switcher = False
    case_insensitive = False

    operator = str(leaf[1])
    left_operand = leaf[0]
    right_operand = leaf[2]

    if operator == "=?":
        if isinstance(right_operand, str):
            right_operand = f"'{right_operand}'"
        return f"({right_operand} in [None, False] or {left_operand} == {right_operand})"

    if operator == "=":
        if right_operand in (False, []):
            return f"not {left_operand}"
        elif right_operand is True:
            return left_operand
        operator = "=="
    elif operator == "!=":
        if right_operand in (False, []):
            return left_operand
        elif right_operand is True:
            return f"not {left_operand}"
    elif "like" in operator:
        case_insensitive = "ilike" in operator
        if isinstance(right_operand, str) and re.search("[_%]", right_operand):
            raise ValueError("Script doesn't support 'like' domains with wildcards")
        if operator in ("=like", "=ilike"):
            operator = "=="
        else:
            operator = "not in" if "not" in operator else "in"
            switcher = True

    if isinstance(right_operand, str):
        right_operand = f"'{right_operand}'"

    if switcher:
        left_operand, right_operand = right_operand, left_operand

    if not case_insensitive:
        stringify = f"{left_operand} {operator} {right_operand}"
    else:
        stringify = f"{left_operand}.lower() {operator} {right_operand}.lower()"

    return stringify


def _stringify_attr(stack):
    """Convert a domain stack (or scalar) to a Python expression string."""
    if stack in (True, False, "True", "False", 1, 0, "1", "0"):
        return str(stack)

    last_paren_idx = max(i for i, item in enumerate(stack[::-1]) if item not in ("|", "!"))
    stack = _normalize_domain(stack)
    stack = stack[::-1]
    result = []

    for index, token in enumerate(stack):
        if token == "!":
            expr = result.pop()
            result.append(f"(not ({expr}))")
        elif token in ("&", "|"):
            left = result.pop()
            try:
                right = result.pop()
            except IndexError:
                res = left + (" and" if token == "&" else " or")
                result.append(res)
                continue
            form = "(%s %s %s)" if index <= last_paren_idx else "%s %s %s"
            result.append(form % (left, "and" if token == "&" else "or", right))
        else:
            result.append(_stringify_leaf(token))

    return result[0]


# ---------------------------------------------------------------------------
# attrs= / states= conversion
# ---------------------------------------------------------------------------

_ESCAPED_OPS = [
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "=?",
    "=like",
    "like",
    "not like",
    "ilike",
    "not ilike",
    "=ilike",
    "in",
    "not in",
    "child_of",
    "parent_of",
]
_OP_PATTERN = "|".join(re.escape(op) for op in _ESCAPED_OPS)


def _get_new_attrs(attrs_str):
    """Parse an attrs= string and return a dict of {attr_name: expression}.

    Only keys matching _NEW_ATTRS are kept; others are silently skipped.
    Returns an empty dict when the string cannot be parsed.
    """
    new_attrs = {}
    # Temporarily replace dynamic variable references so eval() won't fail
    attrs_str = re.sub("&lt;", "<", attrs_str)
    attrs_str = re.sub("&gt;", ">", attrs_str)
    attrs_str = re.sub(
        rf"([\"'](?:{_OP_PATTERN})[\"']\s*,\s*)(?!False|True)([\w\.]+)(?=\s*[\]\)])",
        r"\1'__dynamic_variable__.\2'",
        attrs_str,
    )
    attrs_str = re.sub(r"(%\([\w\.]+\)d)", r"'__dynamic_variable__.\1'", attrs_str)
    attrs_str = attrs_str.strip()

    if not re.search(r"^\{.*\}$", attrs_str, re.DOTALL):
        return new_attrs

    attrs_dict = eval(attrs_str)  # noqa: S307  (safe: literals only)
    for attr, value in attrs_dict.items():
        if attr not in _NEW_ATTRS:
            continue
        stringified = _stringify_attr(value)
        if isinstance(stringified, str):
            stringified = re.sub(r"'__dynamic_variable__\.([^']+)'", r"\1", stringified)
        new_attrs[attr] = stringified

    return new_attrs


def _get_combined_invisible(existing, states_val):
    """Combine an existing invisible expression with a states= value."""

    states = [s.strip() for s in states_val.split(",") if s.strip()]
    state_expr = " or ".join(f"state == '{s}'" for s in states)
    if existing:
        return f"({existing}) or ({state_expr})"
    return state_expr


# ---------------------------------------------------------------------------
# XML tree helpers
# ---------------------------------------------------------------------------


def _get_parent(root, target):
    """Return (index, parent_element, indent) for *target* inside *root*."""
    for parent in root.iter():
        prev = None
        for i, child in enumerate(list(parent)):
            if child is target:
                indent = prev.tail if prev is not None else parent.text
                return i, parent, indent
            prev = child
    return None, None, None


def _child_at(parent, index):
    return list(parent)[index]


def _sibling_attr_tag(doc, node, attr_name):
    """Return the sibling <attribute name=attr_name> element, or None."""
    _, parent, _ = _get_parent(doc, node)
    if parent is None:
        return None
    for child in list(parent):
        if child is not node and child.tag == "attribute" and child.get("name") == attr_name:
            return child
    return None


def _inherited_tag_type(doc, attribute_tag):
    """Return the tag name of the element an <attribute> override targets."""
    _, parent, _ = _get_parent(doc, attribute_tag)
    if parent is None:
        return ""
    return parent.get("name", "")


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------


def _process_file(xml_path, dry_run, auto):
    """Process a single XML file.

    Returns True if the file was (or would be) modified, False otherwise.
    Raises on parse/conversion errors.
    """
    from lxml import etree  # noqa: PLC0415

    raw = xml_path.read_bytes()
    has_encoding_decl = raw.lstrip().startswith(b"<?xml")
    windows_line_endings = b"\r\n" in raw
    if windows_line_endings:
        raw = raw.replace(b"\r\n", b"\n")

    try:
        doc = etree.fromstring(raw)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"XML parse error: {exc}") from exc

    # --- Collect targets ---
    tags_with_attrs = [el for el in doc.iter() if el.get("attrs") is not None]
    tags_with_states = [el for el in doc.iter() if el.get("states") is not None]
    attribute_tags_with_attrs = [
        el for el in doc.iter() if el.tag == "attribute" and el.get("name") == "attrs"
    ]
    attribute_tags_with_states = [
        el for el in doc.iter() if el.tag == "attribute" and el.get("name") == "states"
    ]

    if not any(
        [
            tags_with_attrs,
            tags_with_states,
            attribute_tags_with_attrs,
            attribute_tags_with_states,
        ]
    ):
        return False

    # --- Process attrs= on regular tags ---
    for tag in tags_with_attrs:
        attrs_str = tag.get("attrs", "")
        new_attrs = _get_new_attrs(attrs_str)
        for attr_name, expr in new_attrs.items():
            tag.set(attr_name, str(expr))
        del tag.attrib["attrs"]

    # --- Process states= on regular tags ---
    for tag in tags_with_states:
        states_val = tag.get("states", "")
        existing_invisible = tag.get("invisible", "")
        combined = _get_combined_invisible(existing_invisible, states_val)
        # Rebuild attrib preserving order
        new_attrib = []
        for k, v in list(tag.attrib.items()):
            if k == "invisible" or (k == "states" and not existing_invisible):
                if combined:
                    new_attrib.append(("invisible", combined))
            elif k != "states":
                new_attrib.append((k, v))
        tag.attrib.clear()
        tag.attrib.update(new_attrib)

    # --- Process <attribute name="attrs"> override tags ---
    for attribute_tag in attribute_tags_with_attrs:
        attrs_str = attribute_tag.text or ""
        new_attrs = _get_new_attrs(attrs_str)
        tag_index, parent_tag, indent = _get_parent(doc, attribute_tag)
        tail = attribute_tag.tail

        attribute_tags_to_remove = []
        for attr_name, expr in new_attrs.items():
            existing = _sibling_attr_tag(doc, attribute_tag, attr_name)
            if existing is not None:
                existing.text = str(expr)
                attribute_tags_to_remove.append(attribute_tag)
            else:
                new_tag = etree.Element("attribute", attrib={"name": attr_name})
                new_tag.text = str(expr)
                new_tag.tail = indent
                parent_tag.insert(tag_index, new_tag)
                tag_index += 1

        new_tag.tail = tail  # noqa: F821  (always set — new_attrs not empty here)
        parent_tag.remove(attribute_tag)
        for to_remove in attribute_tags_to_remove:
            ri, rp, _ = _get_parent(doc, to_remove)
            if ri is not None:
                if ri > 0:
                    _child_at(rp, ri - 1).tail = to_remove.tail
                rp.remove(to_remove)

    # --- Process <attribute name="states"> override tags ---
    for attribute_tag in attribute_tags_with_states:
        states_val = attribute_tag.text or ""
        attr_invisible = _sibling_attr_tag(doc, attribute_tag, "invisible")
        tag_index, parent_tag, indent = _get_parent(doc, attribute_tag)

        if attr_invisible is None:
            attr_invisible = etree.Element("attribute", attrib={"name": "invisible"})
            attr_invisible.tail = attribute_tag.tail
            parent_tag.insert(tag_index, attr_invisible)

        existing_invisible = attr_invisible.text or ""
        combined = _get_combined_invisible(existing_invisible, states_val)
        attr_invisible.text = combined
        parent_tag.remove(attribute_tag)

    # --- Preview and confirm ---
    click.echo(f"\n  {xml_path}")
    if not auto:
        if not click.confirm("  Apply changes to this file?", default=False):
            return False

    if not dry_run:
        out = etree.tostring(doc, encoding="utf-8", xml_declaration=has_encoding_decl)
        if windows_line_endings:
            out = out.replace(b"\n", b"\r\n")
        xml_path.write_bytes(out)

    return True


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@command(name="fix-attrs", help=__doc__)
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--auto", is_flag=True, help="Apply changes without per-file confirmation.")
@click.option(
    "--dry-run", is_flag=True, help="Show which files would be changed without modifying them."
)
def main(path: str, auto: bool, dry_run: bool) -> None:
    try:
        from lxml import etree  # noqa: F401, PLC0415
    except ImportError as error:
        raise click.ClickException("lxml is required. Install it with: pip install lxml") from error

    root = Path(path)
    xml_files = sorted(root.rglob("*.xml"))

    if not xml_files:
        click.echo("No XML files found.")
        raise click.exceptions.Exit(0)

    if dry_run:
        click.echo("Dry-run mode — no files will be modified.")

    ok, skipped, failed = [], [], []

    for xml_file in xml_files:
        try:
            changed = _process_file(xml_file, dry_run=dry_run, auto=auto)
            if changed:
                ok.append(xml_file)
            else:
                skipped.append(xml_file)
        except Exception as exc:
            failed.append((xml_file, exc))
            click.echo(
                click.style(f"\n  ✘ {xml_file}: {exc}", fg="red"),
                err=True,
            )

    # --- Summary ---
    click.echo("\n" + "─" * 60)
    if ok:
        label = "Would update" if dry_run else "Updated"
        click.echo(click.style(f"{label}: {len(ok)} file(s)", fg="green"))
        for f in ok:
            click.echo(f"  {f}")
    else:
        click.echo("No files required changes.")

    if failed:
        click.echo(click.style(f"Failed:  {len(failed)} file(s)", fg="red"))
        for f, exc in failed:
            click.echo(f"  {f}: {exc}")
        raise click.exceptions.Exit(1)
