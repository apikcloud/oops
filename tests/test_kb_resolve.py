# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_kb_resolve.py — tests/test_kb_resolve.py

"""Tests for oops/kb/resolve.py."""

from __future__ import annotations

import logging

from oops.kb.resolve import (
    TIER_PRECEDENCE,
    _tier_rank,
    build_depends_chain,
    format_source_line,
    resolve_symbol,
    resolve_symbol_root,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(module: str, origin: str = "odoo", source_file: str = "file.py", source_line: int = 1) -> dict:
    return {"module": module, "origin": origin, "source_file": source_file, "source_line": source_line}


def _index(*edges: tuple[str, str, list[str]]) -> dict:
    """Build a modules_index from (name, origin, depends) tuples."""
    return {name: {"origin": origin, "depends": deps} for name, origin, deps in edges}


# ---------------------------------------------------------------------------
# TestTierRank
# ---------------------------------------------------------------------------


class TestTierRank:
    def test_third_party_is_highest_precedence(self):
        assert _tier_rank("third-party") == 0

    def test_apik_is_second(self):
        assert _tier_rank("apik") == 1

    def test_enterprise_is_third(self):
        assert _tier_rank("enterprise") == 2

    def test_odoo_is_fourth(self):
        assert _tier_rank("odoo") == 3

    def test_unknown_tier_beyond_last(self):
        assert _tier_rank("unknown") == len(TIER_PRECEDENCE)

    def test_all_known_tiers_have_unique_ranks(self):
        ranks = [_tier_rank(t) for t in TIER_PRECEDENCE]
        assert len(set(ranks)) == len(ranks)


# ---------------------------------------------------------------------------
# TestBuildDependsChain
# ---------------------------------------------------------------------------


class TestBuildDependsChain:
    def test_empty_index_returns_empty(self):
        assert build_depends_chain("my_module", {}) == []

    def test_module_not_in_index_returns_empty(self):
        index = _index(("sale", "odoo", []))
        assert build_depends_chain("unknown_module", index) == []

    def test_module_itself_not_in_chain(self):
        index = _index(("my_module", "apik", ["sale"]), ("sale", "odoo", []))
        chain = build_depends_chain("my_module", index)
        assert "my_module" not in chain

    def test_direct_depends_in_chain(self):
        index = _index(("my_module", "apik", ["sale", "account"]), ("sale", "odoo", []), ("account", "odoo", []))
        chain = build_depends_chain("my_module", index)
        assert "sale" in chain
        assert "account" in chain

    def test_direct_depends_before_transitive(self):
        index = _index(
            ("my_module", "apik", ["sale"]),
            ("sale", "odoo", ["account"]),
            ("account", "odoo", []),
        )
        chain = build_depends_chain("my_module", index)
        assert chain.index("sale") < chain.index("account")

    def test_module_with_no_depends_returns_empty(self):
        index = _index(("my_module", "apik", []))
        assert build_depends_chain("my_module", index) == []

    def test_deep_transitive_chain(self):
        index = _index(
            ("my_module", "apik", ["a"]),
            ("a", "odoo", ["b"]),
            ("b", "odoo", ["c"]),
            ("c", "odoo", []),
        )
        chain = build_depends_chain("my_module", index)
        assert chain == ["a", "b", "c"]

    def test_shared_dep_appears_once(self):
        index = _index(
            ("my_module", "apik", ["sale", "account"]),
            ("sale", "odoo", ["base"]),
            ("account", "odoo", ["base"]),
            ("base", "odoo", []),
        )
        chain = build_depends_chain("my_module", index)
        assert chain.count("base") == 1

    def test_cycle_does_not_loop_forever(self):
        index = _index(("a", "odoo", ["b"]), ("b", "odoo", ["a"]))
        chain = build_depends_chain("a", index)
        # "b" is the direct dep; "a" is already visited so cycle stops
        assert chain == ["b"]

    def test_dep_absent_from_index_still_in_chain_but_not_followed(self):
        # A module listed in depends IS added to the chain even if absent from the index;
        # it simply has no transitive deps to follow.
        index = _index(("my_module", "apik", ["sale", "missing_module"]), ("sale", "odoo", []))
        chain = build_depends_chain("my_module", index)
        assert "sale" in chain
        assert "missing_module" in chain  # present in chain
        # But its own transitive deps would not be followed (none in index)
        assert len([m for m in chain if m not in ("sale", "missing_module")]) == 0


# ---------------------------------------------------------------------------
# TestFormatSourceLine
# ---------------------------------------------------------------------------


class TestFormatSourceLine:
    def test_normal_entry(self):
        entry = _entry("sale", origin="odoo", source_file="addons/sale/models/sale_order.py", source_line=234)
        result = format_source_line(entry)
        assert result == "[odoo] addons/sale/models/sale_order.py, line 234"

    def test_missing_origin_uses_question_mark(self):
        assert "?" in format_source_line({"source_file": "f.py", "source_line": 1})

    def test_missing_source_file_uses_question_mark(self):
        assert "?" in format_source_line({"origin": "odoo", "source_line": 1})

    def test_missing_source_line_uses_question_mark(self):
        assert "?" in format_source_line({"origin": "odoo", "source_file": "f.py"})

    def test_empty_entry_all_question_marks(self):
        result = format_source_line({})
        assert result.count("?") >= 3

    def test_third_party_origin(self):
        result = format_source_line({"origin": "third-party", "source_file": "path/to/model.py", "source_line": 10})
        assert result.startswith("[third-party]")


# ---------------------------------------------------------------------------
# TestResolveSymbol
# ---------------------------------------------------------------------------


class TestResolveSymbol:
    def test_empty_entries_returns_none(self):
        assert resolve_symbol([], "my_module", {}) is None

    def test_single_entry_returned_directly(self):
        e = _entry("sale")
        assert resolve_symbol([e], "my_module", {}) is e

    def test_single_entry_from_same_module_returns_none(self):
        # A module cannot report itself as the upstream of its own method.
        e = _entry("my_module")
        assert resolve_symbol([e], "my_module", {}) is None

    def test_same_module_entry_filtered_when_mixed_with_others(self):
        # The self-entry is dropped; the upstream entry from a real dep wins.
        index = _index(("my_module", "apik", ["sale"]), ("sale", "odoo", []))
        self_entry = _entry("my_module", origin="apik")
        upstream = _entry("sale", origin="odoo")
        result = resolve_symbol([self_entry, upstream], "my_module", index)
        assert result is not None
        assert result["module"] == "sale"

    def test_entry_in_depends_chain_wins_over_entry_outside(self):
        index = _index(("my_module", "apik", ["sale"]), ("sale", "odoo", []))
        in_chain = _entry("sale", origin="odoo")
        outside = _entry("account", origin="odoo")
        result = resolve_symbol([outside, in_chain], "my_module", index)
        assert result["module"] == "sale"

    def test_closer_dep_wins_over_farther_dep(self):
        # sale_ext is a direct dep; sale is a transitive dep via sale_ext
        index = _index(
            ("my_module", "apik", ["sale_ext"]),
            ("sale_ext", "third-party", ["sale"]),
            ("sale", "odoo", []),
        )
        closer = _entry("sale_ext", origin="third-party")
        farther = _entry("sale", origin="odoo")
        result = resolve_symbol([farther, closer], "my_module", index)
        assert result["module"] == "sale_ext"

    def test_tier_breaks_tie_when_both_not_in_chain(self):
        # Neither entry is reachable from my_module's depends
        index = _index(("my_module", "apik", []))
        odoo_entry = _entry("sale", origin="odoo")
        apik_entry = _entry("my_other", origin="apik")
        result = resolve_symbol([odoo_entry, apik_entry], "my_module", index)
        # apik (rank 1) beats odoo (rank 3)
        assert result["module"] == "my_other"

    def test_tier_breaks_tie_at_same_chain_position(self):
        # Both modules are direct deps — same position, tier decides
        index = _index(
            ("my_module", "apik", ["tp_mod", "odoo_mod"]),
            ("tp_mod", "third-party", []),
            ("odoo_mod", "odoo", []),
        )
        tp = _entry("tp_mod", origin="third-party")
        odoo = _entry("odoo_mod", origin="odoo")
        result = resolve_symbol([odoo, tp], "my_module", index)
        # third-party (rank 0) beats odoo (rank 3)
        assert result["module"] == "tp_mod"

    def test_returns_none_for_truly_empty(self):
        assert resolve_symbol([], "anything", {"anything": {"origin": "apik", "depends": []}}) is None

    def test_emits_warning_when_winning_module_not_in_chain(self, caplog):
        # Need ≥2 entries: single-entry path returns early without a chain check.
        # Both are outside the chain; third-party wins by tier, warning fires.
        index = _index(("my_module", "apik", []))
        entries = [
            _entry("winner_mod", origin="third-party"),
            _entry("loser_mod", origin="odoo"),
        ]
        with caplog.at_level(logging.WARNING, logger="oops"):
            resolve_symbol(entries, "my_module", index)
        assert any("winner_mod" in msg for msg in caplog.messages)
        assert any("my_module" in msg for msg in caplog.messages)

    def test_no_warning_when_module_is_in_chain(self, caplog):
        index = _index(("my_module", "apik", ["sale"]), ("sale", "odoo", []))
        entries = [_entry("sale", origin="odoo")]
        with caplog.at_level(logging.WARNING, logger="oops"):
            resolve_symbol(entries, "my_module", index)
        assert not caplog.messages

    def test_order_of_input_entries_does_not_affect_result(self):
        index = _index(
            ("my_module", "apik", ["sale"]),
            ("sale", "odoo", ["base"]),
            ("base", "odoo", []),
        )
        in_chain = _entry("sale")
        transitive = _entry("base")
        not_in_chain = _entry("account")
        result_a = resolve_symbol([not_in_chain, transitive, in_chain], "my_module", index)
        result_b = resolve_symbol([in_chain, not_in_chain, transitive], "my_module", index)
        assert result_a["module"] == result_b["module"] == "sale"


# ---------------------------------------------------------------------------
# TestResolveSymbolRoot
# ---------------------------------------------------------------------------


class TestResolveSymbolRoot:
    def test_empty_entries_returns_none(self):
        assert resolve_symbol_root([], "my_module", {}) is None

    def test_single_entry_returned_directly(self):
        e = _entry("sale")
        assert resolve_symbol_root([e], "my_module", {}) is e

    def test_single_entry_from_same_module_returns_none(self):
        e = _entry("my_module")
        assert resolve_symbol_root([e], "my_module", {}) is None

    def test_farther_dep_wins_over_closer_dep(self):
        # project_sequence → project_role → project (core)
        # resolve_symbol picks project_role (closest); resolve_symbol_root picks project (root)
        index = _index(
            ("project_sequence", "third-party", ["project_role"]),
            ("project_role", "third-party", ["project"]),
            ("project", "odoo", []),
        )
        closer = _entry("project_role", origin="third-party")
        farther = _entry("project", origin="odoo")
        result = resolve_symbol_root([closer, farther], "project_sequence", index)
        assert result is not None
        assert result["module"] == "project"

    def test_same_distance_tier_breaks_toward_most_core(self):
        # Both at distance 1 — odoo wins (most core)
        index = _index(
            ("my_module", "apik", ["tp_mod", "odoo_mod"]),
            ("tp_mod", "third-party", []),
            ("odoo_mod", "odoo", []),
        )
        tp = _entry("tp_mod", origin="third-party")
        odoo = _entry("odoo_mod", origin="odoo")
        result = resolve_symbol_root([tp, odoo], "my_module", index)
        assert result is not None
        assert result["module"] == "odoo_mod"

    def test_intermediate_module_ignored_picks_original(self):
        # Mirrors the bug: project_sequence deps include both hr_timesheet (odoo)
        # and project_role (third-party) which both depend on project (odoo).
        # resolve_symbol picks project_role (closest); resolve_symbol_root must
        # pick project (the only entry with no upstream among the candidates).
        index = _index(
            ("project_sequence", "third-party", ["project_role", "hr_timesheet"]),
            ("project_role", "third-party", ["project"]),
            ("hr_timesheet", "odoo", ["project"]),
            ("project", "odoo", []),
        )
        root = _entry("project", origin="odoo")
        intermediate_tp = _entry("project_role", origin="third-party")
        intermediate_core = _entry("hr_timesheet", origin="odoo")
        result = resolve_symbol_root(
            [root, intermediate_tp, intermediate_core], "project_sequence", index
        )
        assert result is not None
        assert result["module"] == "project"

    def test_order_of_input_entries_does_not_affect_result(self):
        index = _index(
            ("my_module", "apik", ["sale_ext"]),
            ("sale_ext", "third-party", ["sale"]),
            ("sale", "odoo", []),
        )
        closer = _entry("sale_ext", origin="third-party")
        farther = _entry("sale", origin="odoo")
        r1 = resolve_symbol_root([closer, farther], "my_module", index)
        r2 = resolve_symbol_root([farther, closer], "my_module", index)
        assert r1 is not None and r2 is not None
        assert r1["module"] == r2["module"] == "sale"


# ---------------------------------------------------------------------------
# TestResolveViewTypes
# ---------------------------------------------------------------------------


class TestResolveViewTypes:
    from oops.kb.build import _resolve_view_types

    def _primary(self, xml_id: str, view_type: str, module: str = "sale") -> dict:
        return {
            "xml_id": xml_id,
            "view_type": view_type,
            "inherit_id": None,
            "mode": "primary",
            "module": module,
        }

    def _extension(self, xml_id: str, inherit_id: str, module: str = "apik") -> dict:
        return {
            "xml_id": xml_id,
            "view_type": None,
            "inherit_id": inherit_id,
            "mode": "extension",
            "module": module,
        }

    def test_primary_view_unchanged(self):
        from oops.kb.build import _resolve_view_types

        v = self._primary("sale.view_form", "form")
        _resolve_view_types([{"views": [v]}])
        assert v["view_type"] == "form"

    def test_extension_inherits_parent_type(self):
        from oops.kb.build import _resolve_view_types

        parent = self._primary("sale.view_form", "form")
        child = self._extension("apik.view_form_ext", "sale.view_form")
        _resolve_view_types([{"views": [parent, child]}])
        assert child["view_type"] == "form"

    def test_cross_layer_resolution(self):
        from oops.kb.build import _resolve_view_types

        global_view = self._primary("sale.view_form", "form", module="sale")
        project_view = self._extension("apik.view_form_ext", "sale.view_form")
        _resolve_view_types([{"views": [global_view]}, {"views": [project_view]}])
        assert project_view["view_type"] == "form"

    def test_chain_resolves_within_depth(self):
        from oops.kb.build import _resolve_view_types

        a = self._primary("sale.view_a", "kanban")
        b = self._extension("mod.view_b", "sale.view_a")
        c = self._extension("mod.view_c", "mod.view_b")
        _resolve_view_types([{"views": [a, b, c]}])
        assert c["view_type"] == "kanban"

    def test_chain_exceeding_depth_resolves_to_unresolved(self):
        from oops.kb.build import _VIEW_TYPE_MAX_DEPTH, _resolve_view_types

        # Build primary + _VIEW_TYPE_MAX_DEPTH extension views.
        # Reversed so the deepest child is processed first (ancestors still None).
        primary = self._primary("root.view", "form", module="base")
        extensions = []
        for i in range(_VIEW_TYPE_MAX_DEPTH + 1):
            parent = "root.view" if i == 0 else f"mod.view_{i - 1}"
            extensions.append(self._extension(f"mod.view_{i}", parent))
        # Process deepest child first so no ancestor is pre-resolved
        views = list(reversed(extensions)) + [primary]
        _resolve_view_types([{"views": views}])
        # Deepest child (views[0] = mod.view_{MAX}) requires MAX+1 hops → unresolved
        assert views[0]["view_type"] == "unresolved"

    def test_cycle_resolves_to_unresolved(self):
        from oops.kb.build import _resolve_view_types

        a = self._extension("mod.view_a", "mod.view_b")
        b = self._extension("mod.view_b", "mod.view_a")
        _resolve_view_types([{"views": [a, b]}])
        assert a["view_type"] == "unresolved"
        assert b["view_type"] == "unresolved"

    def test_missing_parent_resolves_to_unresolved(self):
        from oops.kb.build import _resolve_view_types

        child = self._extension("apik.view_ext", "sale.view_nonexistent")
        _resolve_view_types([{"views": [child]}])
        assert child["view_type"] == "unresolved"

    def test_qweb_template_unchanged(self):
        from oops.kb.build import _resolve_view_types

        tpl = {
            "xml_id": "mod.my_template",
            "view_type": "qweb",
            "inherit_id": None,
            "mode": "primary",
            "module": "mod",
        }
        _resolve_view_types([{"views": [tpl]}])
        assert tpl["view_type"] == "qweb"
