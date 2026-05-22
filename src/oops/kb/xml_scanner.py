# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: xml_scanner.py — oops/kb/xml_scanner.py

"""XML scanner for Odoo source trees.

Indexes ir.ui.view, ir.actions.act_window, ir.ui.menu records (and the
<template>, <act_window>, <menuitem> shorthands) from each module's manifest
data files.

Entry points:
    scan_module_xml(module_dir, origin, tier_root) -> dict
    scan_tier_xml(tier_root, origin, allowed_modules) -> Result[dict]
"""

import json
import xml.etree.ElementTree as ET
import xml.parsers.expat as expat
from pathlib import Path
from typing import Set

from oops.core.logger import log
from oops.core.models import Result
from oops.utils.compat import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

XML_DIR_BLACKLIST = frozenset({"demo", "test", "tests", "static", "migrations", "i18n"})

_VIEW_TAG_ALIASES: Dict[str, str] = {"tree": "list"}

_KNOWN_VIEW_TAGS = frozenset(
    {
        "form",
        "list",
        "tree",
        "search",
        "kanban",
        "pivot",
        "graph",
        "calendar",
        "activity",
        "gantt",
        "map",
        "cohort",
        "qweb",
    }
)

_INDEXED_MODELS = frozenset({"ir.ui.view", "ir.actions.act_window", "ir.ui.menu"})

# ---------------------------------------------------------------------------
# XML parser with line tracking
# ---------------------------------------------------------------------------


def _parse_xml(path: Path) -> Optional[ET.Element]:
    """Parse an XML file with line-number tracking via expat.

    Records source line on every element as the `__line__` attribute.
    Returns the root element or None on failure.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        p = expat.ParserCreate()
        stack: List[ET.Element] = []

        def _start(name: str, attrs: Any) -> None:
            line = p.CurrentLineNumber
            a: Dict[str, str] = {k: v for k, v in attrs.items()}
            a["__line__"] = str(line)
            elem = ET.Element(name, a)
            if stack:
                stack[-1].append(elem)
            stack.append(elem)

        def _end(name: str) -> None:
            if len(stack) > 1:
                stack.pop()

        def _cdata(data: str) -> None:
            if not stack:
                return
            elem = stack[-1]
            if len(elem):
                last = elem[-1]
                last.tail = (last.tail or "") + data
            else:
                elem.text = (elem.text or "") + data

        p.StartElementHandler = _start
        p.EndElementHandler = _end
        p.CharacterDataHandler = _cdata
        p.Parse(source, True)
        return stack[0] if stack else None
    except expat.ExpatError as exc:
        log.warning("XML parse error in %s: %s", path, exc)
    except Exception as exc:
        log.warning("Cannot read %s: %s", path, exc)
    return None


def _line_of(elem: ET.Element) -> int:
    val = elem.get("__line__")
    return int(val) if val else 0


# ---------------------------------------------------------------------------
# Manifest fallback helper
# ---------------------------------------------------------------------------


def _load_manifest_or_fallback(module_dir: Path) -> Optional[dict]:
    """Return manifest dict, or None to signal "fall back to recursive scan".

    - Returns dict (possibly empty) when manifest is readable.
    - Returns None when manifest exists but cannot be parsed.
    - Returns {} when no manifest file is found.
    """
    from oops.core.config import config
    from oops.io.manifest import parse_manifest

    for manifest_name in config.manifest_names:
        path = module_dir / manifest_name
        if path.is_file():
            try:
                return parse_manifest(path)
            except Exception as exc:
                log.warning(
                    "Manifest parse failure in %s: %s — falling back to recursive XML scan",
                    path,
                    exc,
                )
                return None
    return {}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _is_blacklisted(rel: Path) -> bool:
    return any(part in XML_DIR_BLACKLIST for part in rel.parts)


def _recursive_xml_files(module_dir: Path) -> List[Path]:
    out: List[Path] = []
    for path in module_dir.rglob("*.xml"):
        rel = path.relative_to(module_dir)
        if _is_blacklisted(rel):
            continue
        out.append(path)
    return out


def _discover_xml_files(module_dir: Path) -> List[Path]:
    """Decide which XML files to scan in a module.

    Strategy:
        1. Read manifest. If present and has `data`, use those entries.
           Exclude any entry that also appears in `demo`.
        2. If manifest is unparseable (None), recursively scan `*.xml`.
        3. If no `data` key, recursively scan `*.xml`.
        4. Apply XML_DIR_BLACKLIST in all cases.
        5. Keep only `.xml` files that exist.
    """
    manifest = _load_manifest_or_fallback(module_dir)
    if manifest is None:
        return _recursive_xml_files(module_dir)

    data_entries = manifest.get("data", []) or []
    demo_entries = set(manifest.get("demo", []) or [])

    if not data_entries:
        return _recursive_xml_files(module_dir)

    out: List[Path] = []
    for entry in data_entries:
        if entry in demo_entries:
            continue
        if not entry.endswith(".xml"):
            continue
        rel = Path(entry)
        if _is_blacklisted(rel):
            continue
        absolute = module_dir / rel
        if absolute.is_file():
            out.append(absolute)
    return out


# ---------------------------------------------------------------------------
# XML id qualification
# ---------------------------------------------------------------------------


def _qualify(raw: str, module: str) -> str:
    """Module-qualify an xml_id. If `raw` contains a dot, return as-is."""
    if not raw:
        return raw
    if "." in raw:
        return raw
    return f"{module}.{raw}"


def _qualify_optional(val: Optional[str], module: str) -> Optional[str]:
    return _qualify(val, module) if val else None


# ---------------------------------------------------------------------------
# Field / button extraction
# ---------------------------------------------------------------------------


def _strip_action_ref(name: str) -> str:
    # "%(account.action_invoice)s" → "account.action_invoice"
    if name.startswith("%(") and name.endswith(")s"):
        return name[2:-2]
    return name


def _extract_content(
    arch: ET.Element,
    view_type: Optional[str],
) -> Tuple[List[str], List[Dict[str, str]]]:
    if view_type == "qweb":
        return [], []
    seen_fields: List[str] = []
    seen_fields_set: set = set()
    # arch is <field name="arch">; iterate its children to avoid matching arch itself
    for view_root in arch:
        for f in view_root.iter("field"):
            n = f.get("name")
            if n and n not in seen_fields_set:
                seen_fields.append(n)
                seen_fields_set.add(n)
    buttons: List[Dict[str, str]] = []
    for view_root in arch:
        for b in view_root.iter("button"):
            btype = b.get("type")
            if btype not in ("object", "action"):
                continue
            bname = b.get("name")
            if not bname:
                continue
            if btype == "action":
                bname = _strip_action_ref(bname)
            buttons.append({"button_type": btype, "name": bname})
    return seen_fields, buttons


# ---------------------------------------------------------------------------
# View record extraction helpers
# ---------------------------------------------------------------------------


def _extract_record_field(record: ET.Element, name: str) -> Optional[str]:
    """Return the text value (or `ref=` value) of a `<field name=NAME>` child."""
    for field in record.findall("field"):
        if field.get("name") == name:
            ref = field.get("ref")
            if ref:
                return ref
            return (field.text or "").strip() or None
    return None


def _find_arch(record: ET.Element) -> Optional[ET.Element]:
    for field in record.findall("field"):
        if field.get("name") == "arch":
            return field
    return None


def _primary_view_type(arch: ET.Element) -> Optional[str]:
    for child in arch:
        tag = _VIEW_TAG_ALIASES.get(child.tag, child.tag)
        return tag if tag in _KNOWN_VIEW_TAGS else None
    return None


# ---------------------------------------------------------------------------
# Record parsers
# ---------------------------------------------------------------------------


def _parse_view_record(
    record: ET.Element,
    module: str,
    origin: str,
    rel_path: str,
) -> Optional[Dict[str, Any]]:
    raw_id = record.get("id")
    if not raw_id:
        log.warning("View record missing id in %s:%d", rel_path, _line_of(record))
        return None

    xml_id = _qualify(raw_id, module)
    name = _extract_record_field(record, "name")
    model = _extract_record_field(record, "model")
    inherit_ref = _extract_record_field(record, "inherit_id")
    inherit_id = _qualify(inherit_ref, module) if inherit_ref else None
    mode_val = _extract_record_field(record, "mode")
    mode = mode_val or ("extension" if inherit_id else "primary")

    arch = _find_arch(record)
    view_type: Optional[str]
    if inherit_id and mode != "primary":
        view_type = None  # extension — resolved in pass 2
    else:
        view_type = _primary_view_type(arch) if arch is not None else None

    fields, buttons = _extract_content(arch, view_type) if arch is not None else ([], [])

    return {
        "xml_id": xml_id,
        "name": name,
        "model": model,
        "view_type": view_type,
        "inherit_id": inherit_id,
        "mode": mode,
        "origin": origin,
        "module": module,
        "source_file": rel_path,
        "source_line": _line_of(record),
        "fields_json": json.dumps(fields),
        "buttons_json": json.dumps(buttons),
    }


def _parse_template(
    elem: ET.Element,
    module: str,
    origin: str,
    rel_path: str,
) -> Optional[Dict[str, Any]]:
    raw_id = elem.get("id")
    if not raw_id:
        log.warning("Template missing id in %s:%d", rel_path, _line_of(elem))
        return None
    inherit_ref = elem.get("inherit_id")
    inherit_id = _qualify(inherit_ref, module) if inherit_ref else None
    mode = "extension" if inherit_id else "primary"
    return {
        "xml_id": _qualify(raw_id, module),
        "name": elem.get("name"),
        "model": None,
        "view_type": "qweb",
        "inherit_id": inherit_id,
        "mode": mode,
        "origin": origin,
        "module": module,
        "source_file": rel_path,
        "source_line": _line_of(elem),
        "fields_json": json.dumps([]),
        "buttons_json": json.dumps([]),
    }


def _parse_action_record(
    record: ET.Element,
    module: str,
    origin: str,
    rel_path: str,
) -> Optional[Dict[str, Any]]:
    raw_id = record.get("id")
    if not raw_id:
        log.warning("Action record missing id in %s:%d", rel_path, _line_of(record))
        return None
    return {
        "xml_id": _qualify(raw_id, module),
        "name": _extract_record_field(record, "name"),
        "model": _extract_record_field(record, "res_model"),
        "view_id": _qualify_optional(_extract_record_field(record, "view_id"), module),
        "domain": _extract_record_field(record, "domain"),
        "origin": origin,
        "module": module,
        "source_file": rel_path,
        "source_line": _line_of(record),
    }


def _parse_act_window_shorthand(
    elem: ET.Element,
    module: str,
    origin: str,
    rel_path: str,
) -> Optional[Dict[str, Any]]:
    raw_id = elem.get("id")
    if not raw_id:
        return None
    return {
        "xml_id": _qualify(raw_id, module),
        "name": elem.get("name"),
        "model": elem.get("res_model"),
        "view_id": _qualify_optional(elem.get("view_id"), module),
        "domain": elem.get("domain"),
        "origin": origin,
        "module": module,
        "source_file": rel_path,
        "source_line": _line_of(elem),
    }


def _parse_menu_record(
    record: ET.Element,
    module: str,
    origin: str,
    rel_path: str,
) -> Optional[Dict[str, Any]]:
    raw_id = record.get("id")
    if not raw_id:
        return None
    return {
        "xml_id": _qualify(raw_id, module),
        "name": _extract_record_field(record, "name"),
        "action": _qualify_optional(_extract_record_field(record, "action"), module),
        "parent_id": _qualify_optional(_extract_record_field(record, "parent_id"), module),
        "origin": origin,
        "module": module,
        "source_file": rel_path,
        "source_line": _line_of(record),
    }


def _parse_menuitem_shorthand(
    elem: ET.Element,
    module: str,
    origin: str,
    rel_path: str,
) -> Optional[Dict[str, Any]]:
    raw_id = elem.get("id")
    if not raw_id:
        return None
    return {
        "xml_id": _qualify(raw_id, module),
        "name": elem.get("name"),
        "action": _qualify_optional(elem.get("action"), module),
        "parent_id": _qualify_optional(elem.get("parent"), module),
        "origin": origin,
        "module": module,
        "source_file": rel_path,
        "source_line": _line_of(elem),
    }


# ---------------------------------------------------------------------------
# Top-level entry points
# ---------------------------------------------------------------------------


def _scan_xml_file(
    root: ET.Element,
    module: str,
    origin: str,
    rel_path: str,
    result: Dict[str, Any],
) -> None:
    """Extract all indexed records from a parsed XML root into result."""
    for record in root.iter("record"):
        model = record.get("model")
        if model not in _INDEXED_MODELS:
            continue
        if model == "ir.ui.view":
            rec = _parse_view_record(record, module, origin, rel_path)
            if rec:
                result["views"].append(rec)
        elif model == "ir.actions.act_window":
            rec = _parse_action_record(record, module, origin, rel_path)
            if rec:
                result["actions"].append(rec)
        elif model == "ir.ui.menu":
            rec = _parse_menu_record(record, module, origin, rel_path)
            if rec:
                result["menus"].append(rec)

    for tpl in root.iter("template"):
        rec = _parse_template(tpl, module, origin, rel_path)
        if rec:
            result["views"].append(rec)

    for elem in root.iter("act_window"):
        rec = _parse_act_window_shorthand(elem, module, origin, rel_path)
        if rec:
            result["actions"].append(rec)

    for elem in root.iter("menuitem"):
        rec = _parse_menuitem_shorthand(elem, module, origin, rel_path)
        if rec:
            result["menus"].append(rec)


def scan_module_xml(
    module_dir: Path,
    origin: str,
    tier_root: Path,
) -> Dict[str, Any]:
    """Scan all XML data files in a module.

    Returns a dict with keys 'views', 'actions', 'menus' — each a list of
    record dicts. Empty lists if no XML files or all records ignored.
    """
    module = module_dir.name
    result: Dict[str, Any] = {"views": [], "actions": [], "menus": []}

    for xml_file in _discover_xml_files(module_dir):
        try:
            rel_path = str(xml_file.relative_to(tier_root))
        except ValueError:
            rel_path = str(xml_file)

        root = _parse_xml(xml_file)
        if root is None:
            continue

        _scan_xml_file(root, module, origin, rel_path, result)

    return result


def scan_tier_xml(
    tier_root: Path,
    origin: str,
    allowed_modules: Optional[Set[str]] = None,
) -> "Result[Dict[str, Any]]":
    """Scan XML for all addon modules under tier_root.

    Mirrors scanner.scan_tier — same iteration, same gates.
    """
    from oops.io.manifest import load_manifest

    merged: Dict[str, Any] = {"views": [], "actions": [], "menus": []}
    result: "Result[Dict[str, Any]]" = Result()

    if not tier_root.is_dir():
        result.add_warning(f"Tier root not found, skipping: {tier_root}")
        result.data = merged
        return result

    for entry in sorted(tier_root.iterdir()):
        if not entry.is_dir():
            continue
        if allowed_modules and entry.name not in allowed_modules:
            continue
        if not load_manifest(entry):
            continue
        data = scan_module_xml(entry, origin, tier_root)
        merged["views"].extend(data["views"])
        merged["actions"].extend(data["actions"])
        merged["menus"].extend(data["menus"])

    result.data = merged
    return result
