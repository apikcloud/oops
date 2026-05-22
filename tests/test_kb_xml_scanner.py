# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_kb_xml_scanner.py — tests/test_kb_xml_scanner.py

"""Unit tests for oops/kb/xml_scanner.py."""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from oops.kb.xml_scanner import (
    _discover_xml_files,
    _extract_content,
    _line_of,
    _load_manifest_or_fallback,
    _primary_view_type,
    _qualify,
    scan_module_xml,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_manifest(module_dir: Path, content: str) -> Path:
    p = module_dir / "__manifest__.py"
    p.write_text(content)
    return p


def _write_xml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _odoo_xml(body: str) -> str:
    return f'<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n{body}\n</odoo>\n'


# ---------------------------------------------------------------------------
# TestManifestFallback
# ---------------------------------------------------------------------------


class TestManifestFallback:
    def test_no_manifest_returns_empty_dict(self, tmp_path):
        result = _load_manifest_or_fallback(tmp_path)
        assert result == {}

    def test_valid_manifest_returns_dict(self, tmp_path):
        _write_manifest(tmp_path, "{'name': 'My Module', 'data': ['views/form.xml']}")
        result = _load_manifest_or_fallback(tmp_path)
        assert isinstance(result, dict)
        assert result["name"] == "My Module"

    def test_unparseable_manifest_returns_none(self, tmp_path):
        (tmp_path / "__manifest__.py").write_text("{{not valid python{{")
        result = _load_manifest_or_fallback(tmp_path)
        assert result is None

    def test_manifest_not_dict_returns_none(self, tmp_path):
        # ast.literal_eval succeeds but returns non-dict → parse_manifest returns {}
        # That is treated as "readable but empty" → returns {}
        (tmp_path / "__manifest__.py").write_text("[1, 2, 3]")
        result = _load_manifest_or_fallback(tmp_path)
        # parse_manifest returns {} for non-dict → _load_manifest_or_fallback returns {}
        assert result == {}


# ---------------------------------------------------------------------------
# TestFileDiscovery
# ---------------------------------------------------------------------------


class TestFileDiscovery:
    def test_uses_manifest_data_entries(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/form.xml']}")
        _write_xml(tmp_path / "views" / "form.xml", _odoo_xml(""))
        _write_xml(tmp_path / "views" / "other.xml", _odoo_xml(""))
        result = _discover_xml_files(tmp_path)
        assert len(result) == 1
        assert result[0].name == "form.xml"

    def test_excludes_demo_entries(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/form.xml', 'demo/data.xml'], 'demo': ['demo/data.xml']}")
        _write_xml(tmp_path / "views" / "form.xml", _odoo_xml(""))
        _write_xml(tmp_path / "demo" / "data.xml", _odoo_xml(""))
        result = _discover_xml_files(tmp_path)
        assert len(result) == 1
        assert result[0].name == "form.xml"

    def test_skips_nonxml_entries(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['security/ir.model.access.csv', 'views/form.xml']}")
        _write_xml(tmp_path / "views" / "form.xml", _odoo_xml(""))
        result = _discover_xml_files(tmp_path)
        assert len(result) == 1

    def test_blacklist_applied_to_data_entries(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['tests/test_data.xml', 'views/form.xml']}")
        _write_xml(tmp_path / "tests" / "test_data.xml", _odoo_xml(""))
        _write_xml(tmp_path / "views" / "form.xml", _odoo_xml(""))
        result = _discover_xml_files(tmp_path)
        assert len(result) == 1
        assert result[0].name == "form.xml"

    def test_recursive_scan_when_no_data_key(self, tmp_path):
        _write_manifest(tmp_path, "{'name': 'mod'}")
        _write_xml(tmp_path / "views" / "form.xml", _odoo_xml(""))
        _write_xml(tmp_path / "views" / "list.xml", _odoo_xml(""))
        result = _discover_xml_files(tmp_path)
        assert len(result) == 2

    def test_recursive_scan_excludes_blacklisted_dirs(self, tmp_path):
        _write_manifest(tmp_path, "{'name': 'mod'}")
        _write_xml(tmp_path / "views" / "form.xml", _odoo_xml(""))
        _write_xml(tmp_path / "static" / "src" / "view.xml", _odoo_xml(""))
        _write_xml(tmp_path / "tests" / "test.xml", _odoo_xml(""))
        result = _discover_xml_files(tmp_path)
        assert len(result) == 1
        assert result[0].name == "form.xml"

    def test_recursive_scan_on_unparseable_manifest(self, tmp_path):
        (tmp_path / "__manifest__.py").write_text("{{bad")
        _write_xml(tmp_path / "views" / "form.xml", _odoo_xml(""))
        result = _discover_xml_files(tmp_path)
        assert len(result) == 1

    def test_missing_file_in_data_skipped(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/missing.xml']}")
        result = _discover_xml_files(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# TestQualification
# ---------------------------------------------------------------------------


class TestQualification:
    def test_qualify_without_dot(self):
        assert _qualify("my_view", "sale") == "sale.my_view"

    def test_qualify_with_dot_is_noop(self):
        assert _qualify("sale.my_view", "purchase") == "sale.my_view"

    def test_qualify_empty_string(self):
        assert _qualify("", "sale") == ""


# ---------------------------------------------------------------------------
# TestPrimaryViewType
# ---------------------------------------------------------------------------


class TestPrimaryViewType:
    def _arch(self, tag: str) -> ET.Element:
        arch = ET.fromstring(f"<field name='arch'><{tag}/></field>")
        return arch

    def test_form(self):
        assert _primary_view_type(self._arch("form")) == "form"

    def test_tree_aliased_to_list(self):
        assert _primary_view_type(self._arch("tree")) == "list"

    def test_list(self):
        assert _primary_view_type(self._arch("list")) == "list"

    def test_kanban(self):
        assert _primary_view_type(self._arch("kanban")) == "kanban"

    def test_unknown_tag_returns_none(self):
        assert _primary_view_type(self._arch("custom_view")) is None

    def test_filter_tag_returns_none(self):
        assert _primary_view_type(self._arch("filter")) is None

    def test_xpath_tag_returns_none(self):
        assert _primary_view_type(self._arch("xpath")) is None

    def test_cohort(self):
        assert _primary_view_type(self._arch("cohort")) == "cohort"

    def test_qweb(self):
        assert _primary_view_type(self._arch("qweb")) == "qweb"

    def test_empty_arch_returns_none(self):
        arch = ET.fromstring("<field name='arch'></field>")
        assert _primary_view_type(arch) is None


# ---------------------------------------------------------------------------
# TestContentExtraction
# ---------------------------------------------------------------------------


class TestContentExtraction:
    def _arch(self, xml: str) -> ET.Element:
        return ET.fromstring(xml)

    def test_fields_extracted(self):
        arch = self._arch("<field name='arch'><form><field name='name'/><field name='partner_id'/></form></field>")
        fields, buttons = _extract_content(arch, "form")
        assert fields == ["name", "partner_id"]
        assert buttons == []

    def test_nested_fields_extracted(self):
        arch = self._arch(
            "<field name='arch'><form><sheet><group>"
            "<field name='name'/><field name='amount'/>"
            "</group></sheet></form></field>"
        )
        fields, _ = _extract_content(arch, "form")
        assert "name" in fields
        assert "amount" in fields

    def test_duplicate_fields_deduplicated(self):
        arch = self._arch("<field name='arch'><form><field name='name'/><field name='name'/></form></field>")
        fields, _ = _extract_content(arch, "form")
        assert fields.count("name") == 1

    def test_button_object_extracted(self):
        arch = self._arch("<field name='arch'><form><button type='object' name='action_confirm'/></form></field>")
        _, buttons = _extract_content(arch, "form")
        assert len(buttons) == 1
        assert buttons[0] == {"button_type": "object", "name": "action_confirm"}

    def test_button_action_with_ref_stripped(self):
        arch = self._arch(
            "<field name='arch'><form><button type='action' name='%(account.action_invoice)s'/></form></field>"
        )
        _, buttons = _extract_content(arch, "form")
        assert buttons[0]["name"] == "account.action_invoice"

    def test_button_unknown_type_ignored(self):
        arch = self._arch("<field name='arch'><form><button type='url' name='google'/></form></field>")
        _, buttons = _extract_content(arch, "form")
        assert buttons == []

    def test_qweb_returns_empty(self):
        arch = self._arch("<field name='arch'><t><field name='name'/></t></field>")
        fields, buttons = _extract_content(arch, "qweb")
        assert fields == []
        assert buttons == []


# ---------------------------------------------------------------------------
# TestRecordExtraction
# ---------------------------------------------------------------------------


class TestRecordExtraction:
    def test_view_record_primary_form(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/form.xml']}")
        _write_xml(
            tmp_path / "views" / "form.xml",
            _odoo_xml(
                """<record id="view_order_form" model="ir.ui.view">
                    <field name="name">sale.order.form</field>
                    <field name="model">sale.order</field>
                    <field name="arch" type="xml">
                        <form><field name="name"/></form>
                    </field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert len(result["views"]) == 1
        v = result["views"][0]
        assert v["xml_id"] == "tmp_path.view_order_form".replace("tmp_path", tmp_path.name)
        assert v["model"] == "sale.order"
        assert v["view_type"] == "form"
        assert v["mode"] == "primary"
        assert v["inherit_id"] is None
        assert json.loads(v["fields_json"]) == ["name"]

    def test_view_record_extension(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/ext.xml']}")
        _write_xml(
            tmp_path / "views" / "ext.xml",
            _odoo_xml(
                """<record id="view_order_form_ext" model="ir.ui.view">
                    <field name="inherit_id" ref="sale.view_order_form"/>
                    <field name="arch" type="xml">
                        <xpath expr="//field[@name='name']" position="after">
                            <field name="ref"/>
                        </xpath>
                    </field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "apik", tmp_path.parent)
        assert len(result["views"]) == 1
        v = result["views"][0]
        assert v["view_type"] is None  # extension, unresolved
        assert v["mode"] == "extension"
        assert v["inherit_id"] == "sale.view_order_form"

    def test_view_record_explicit_primary_mode(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/form.xml']}")
        _write_xml(
            tmp_path / "views" / "form.xml",
            _odoo_xml(
                """<record id="view_order_form_primary" model="ir.ui.view">
                    <field name="inherit_id" ref="sale.view_order_form"/>
                    <field name="mode">primary</field>
                    <field name="arch" type="xml">
                        <form><field name="name"/></form>
                    </field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "apik", tmp_path.parent)
        v = result["views"][0]
        assert v["mode"] == "primary"
        assert v["view_type"] == "form"  # explicit primary → extract view type

    def test_action_record(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['actions/act.xml']}")
        _write_xml(
            tmp_path / "actions" / "act.xml",
            _odoo_xml(
                """<record id="action_orders" model="ir.actions.act_window">
                    <field name="name">Sales Orders</field>
                    <field name="res_model">sale.order</field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert len(result["actions"]) == 1
        a = result["actions"][0]
        assert a["xml_id"].endswith(".action_orders")
        assert a["model"] == "sale.order"
        assert a["name"] == "Sales Orders"

    def test_menu_record(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['menus/menu.xml']}")
        _write_xml(
            tmp_path / "menus" / "menu.xml",
            _odoo_xml(
                """<record id="menu_root" model="ir.ui.menu">
                    <field name="name">Sales</field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert len(result["menus"]) == 1
        m = result["menus"][0]
        assert m["xml_id"].endswith(".menu_root")
        assert m["name"] == "Sales"


# ---------------------------------------------------------------------------
# TestShorthands
# ---------------------------------------------------------------------------


class TestShorthands:
    def test_template_shorthand(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/tpl.xml']}")
        _write_xml(
            tmp_path / "views" / "tpl.xml",
            _odoo_xml('<template id="my_template"><t t-name="test"/></template>'),
        )
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert len(result["views"]) == 1
        v = result["views"][0]
        assert v["view_type"] == "qweb"
        assert v["mode"] == "primary"
        assert v["xml_id"].endswith(".my_template")

    def test_template_with_inherit_id(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/tpl.xml']}")
        _write_xml(
            tmp_path / "views" / "tpl.xml",
            _odoo_xml('<template id="ext" inherit_id="base.my_template"/>'),
        )
        result = scan_module_xml(tmp_path, "apik", tmp_path.parent)
        v = result["views"][0]
        assert v["mode"] == "extension"
        assert v["inherit_id"] == "base.my_template"

    def test_act_window_shorthand(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['actions/act.xml']}")
        _write_xml(
            tmp_path / "actions" / "act.xml",
            _odoo_xml('<act_window id="action_sale" name="Sales" res_model="sale.order"/>'),
        )
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert len(result["actions"]) == 1
        a = result["actions"][0]
        assert a["xml_id"].endswith(".action_sale")
        assert a["model"] == "sale.order"

    def test_menuitem_shorthand(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['menus/menu.xml']}")
        _write_xml(
            tmp_path / "menus" / "menu.xml",
            _odoo_xml('<menuitem id="menu_sale" name="Sales" action="%(sale.action_orders)s"/>'),
        )
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert len(result["menus"]) == 1
        m = result["menus"][0]
        assert m["xml_id"].endswith(".menu_sale")

    def test_menuitem_parent_qualified(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['menus/menu.xml']}")
        _write_xml(
            tmp_path / "menus" / "menu.xml",
            _odoo_xml('<menuitem id="menu_child" name="Child" parent="menu_root"/>'),
        )
        result = scan_module_xml(tmp_path, "mymod", tmp_path.parent)
        m = result["menus"][0]
        # unqualified parent → module-qualified
        assert m["parent_id"] == f"{tmp_path.name}.menu_root"


# ---------------------------------------------------------------------------
# TestExtensionView
# ---------------------------------------------------------------------------


class TestExtensionView:
    def test_extension_view_has_none_view_type(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/ext.xml']}")
        _write_xml(
            tmp_path / "views" / "ext.xml",
            _odoo_xml(
                """<record id="ext" model="ir.ui.view">
                    <field name="inherit_id" ref="sale.view_order_form"/>
                    <field name="arch" type="xml"><xpath/></field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "apik", tmp_path.parent)
        assert result["views"][0]["view_type"] is None

    def test_primary_mode_overrides_inherit_id(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/ext.xml']}")
        _write_xml(
            tmp_path / "views" / "ext.xml",
            _odoo_xml(
                """<record id="ext" model="ir.ui.view">
                    <field name="inherit_id" ref="sale.view_order_form"/>
                    <field name="mode">primary</field>
                    <field name="arch" type="xml"><form/></field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "apik", tmp_path.parent)
        v = result["views"][0]
        assert v["mode"] == "primary"
        assert v["view_type"] == "form"


# ---------------------------------------------------------------------------
# TestErrorHandling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_malformed_xml_logs_warning_and_skips(self, tmp_path, caplog):
        _write_manifest(tmp_path, "{'data': ['views/bad.xml']}")
        _write_xml(tmp_path / "views" / "bad.xml", "<odoo><unclosed>")
        with caplog.at_level(logging.WARNING, logger="oops"):
            result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert result == {"views": [], "actions": [], "menus": []}
        assert any("bad.xml" in msg for msg in caplog.messages)

    def test_view_missing_id_logged_and_skipped(self, tmp_path, caplog):
        _write_manifest(tmp_path, "{'data': ['views/form.xml']}")
        _write_xml(
            tmp_path / "views" / "form.xml",
            _odoo_xml(
                """<record model="ir.ui.view">
                    <field name="arch" type="xml"><form/></field>
                </record>"""
            ),
        )
        with caplog.at_level(logging.WARNING, logger="oops"):
            result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert result["views"] == []
        assert any("missing id" in msg.lower() for msg in caplog.messages)

    def test_view_missing_model_field_is_none_not_skipped(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/form.xml']}")
        _write_xml(
            tmp_path / "views" / "form.xml",
            _odoo_xml(
                """<record id="my_view" model="ir.ui.view">
                    <field name="arch" type="xml"><form/></field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert len(result["views"]) == 1
        assert result["views"][0]["model"] is None

    def test_non_indexed_model_ignored(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['data/data.xml']}")
        _write_xml(
            tmp_path / "data" / "data.xml",
            _odoo_xml(
                """<record id="my_seq" model="ir.sequence">
                    <field name="name">My Sequence</field>
                </record>"""
            ),
        )
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert result == {"views": [], "actions": [], "menus": []}


# ---------------------------------------------------------------------------
# TestSourceLines
# ---------------------------------------------------------------------------


class TestSourceLines:
    def test_line_numbers_captured(self, tmp_path):
        _write_manifest(tmp_path, "{'data': ['views/form.xml']}")
        xml_content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<odoo>\n"
            '  <record id="view_form" model="ir.ui.view">\n'
            '    <field name="arch" type="xml"><form/></field>\n'
            "  </record>\n"
            "</odoo>\n"
        )
        (tmp_path / "views").mkdir()
        (tmp_path / "views" / "form.xml").write_text(xml_content)
        result = scan_module_xml(tmp_path, "odoo", tmp_path.parent)
        assert len(result["views"]) == 1
        assert result["views"][0]["source_line"] == 3

    def test_line_of_returns_zero_for_missing(self):
        elem = ET.fromstring("<record/>")
        assert _line_of(elem) == 0
