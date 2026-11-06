# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_kb_provenance.py — tests/test_kb_provenance.py

"""Tests for oops/kb/provenance.py — the unified origin vocabulary."""

from __future__ import annotations

import pytest
from oops_engine.exceptions import ClassificationConflict
from oops_engine.provenance import (
    ORIGIN_CORE,
    ORIGIN_CUSTOM,
    ORIGIN_ENTERPRISE,
    ORIGIN_OCA,
    ORIGIN_THIRD_PARTY,
    ORIGINS,
    classify_addon,
    match_classification,
    normalize_origin,
)


def test_origins_has_exactly_five_members() -> None:
    assert ORIGINS == {
        ORIGIN_CORE,
        ORIGIN_ENTERPRISE,
        ORIGIN_OCA,
        ORIGIN_THIRD_PARTY,
        ORIGIN_CUSTOM,
    }
    assert len(ORIGINS) == 5


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("odoo", ORIGIN_CORE),
        ("odoo_core", ORIGIN_CORE),
        ("community", ORIGIN_CORE),
        ("themes", ORIGIN_CORE),
        ("enterprise", ORIGIN_ENTERPRISE),
        ("third-party", ORIGIN_THIRD_PARTY),
        ("third_party", ORIGIN_THIRD_PARTY),
        ("oca", ORIGIN_OCA),
        ("custom", ORIGIN_CUSTOM),
        ("project", ORIGIN_CUSTOM),
    ],
)
def test_normalize_origin_maps_every_legacy_label(raw: str, expected: str) -> None:
    assert normalize_origin(raw) == expected
    assert normalize_origin(raw) in ORIGINS


def test_normalize_origin_preserves_none_and_empty() -> None:
    assert normalize_origin(None) is None
    assert normalize_origin("") == ""


def test_normalize_origin_unknown_falls_back_to_third_party() -> None:
    assert normalize_origin("something-weird") == ORIGIN_THIRD_PARTY


def test_normalize_origin_retired_tier_labels_fall_back_to_third_party() -> None:
    # "apik"/"local" were removed as tier labels; they are now just unknown input.
    assert normalize_origin("apik") == ORIGIN_THIRD_PARTY
    assert normalize_origin("local") == ORIGIN_THIRD_PARTY


def test_no_legacy_string_leaks() -> None:
    # The mapper must never emit a legacy variant.
    for raw in ("odoo", "third-party", "community"):
        assert normalize_origin(raw) not in {"odoo", "third-party", "community"}


class TestClassifyAddon:
    def test_oca_by_author(self) -> None:
        assert classify_addon("Odoo Community Association (OCA)", "server_tools", "") == "oca"

    def test_custom_by_author(self) -> None:
        assert classify_addon("Apik", "some_module", "", project_author="Apik") == "custom"

    def test_custom_by_prefix(self) -> None:
        assert classify_addon("Someone", "apk_sale_extension", "", project_prefix="apk_") == "custom"

    def test_oca_by_org(self) -> None:
        assert classify_addon("Someone", "server_tools", "OCA") == "oca"

    def test_custom_by_org(self) -> None:
        assert classify_addon("Someone", "my_module", "apik-cloud", github_owner="apik-cloud") == "custom"

    def test_fallback_third_party(self) -> None:
        assert classify_addon("Someone Else", "unrelated_module", "") == "third-party"

    def test_oca_by_author_wins_over_org(self) -> None:
        result = classify_addon("Odoo Community Association (OCA)", "m", "apik-cloud", github_owner="apik-cloud")
        assert result == "oca"


class TestClassifyAddonOverrides:
    def test_no_overrides_keeps_heuristics(self) -> None:
        for overrides in (None, {}):
            assert classify_addon("Someone", "legacy_mail", "", overrides=overrides) == "third-party"

    def test_glob_promotes_to_custom(self) -> None:
        overrides = {"custom": ["legacy_*"]}
        assert classify_addon("Someone", "legacy_mail", "", overrides=overrides) == "custom"

    def test_exact_name_promotes_to_custom(self) -> None:
        overrides = {"custom": ["unprefixed_addon"]}
        assert classify_addon("Someone", "unprefixed_addon", "", overrides=overrides) == "custom"

    def test_can_demote_prefixed_addon(self) -> None:
        overrides = {"third-party": ["apk_vendored"]}
        result = classify_addon("Someone", "apk_vendored", "", project_prefix="apk_", overrides=overrides)
        assert result == "third-party"

    def test_wins_over_project_author(self) -> None:
        overrides = {"third-party": ["some_module"]}
        result = classify_addon("Apik", "some_module", "", project_author="Apik", overrides=overrides)
        assert result == "third-party"

    def test_wins_over_oca_author(self) -> None:
        overrides = {"custom": ["server_tools"]}
        result = classify_addon("Odoo Community Association (OCA)", "server_tools", "", overrides=overrides)
        assert result == "custom"

    def test_wins_over_submodule_org(self) -> None:
        overrides = {"custom": ["server_tools"]}
        assert classify_addon("Someone", "server_tools", "OCA", overrides=overrides) == "custom"

    def test_unmatched_addon_falls_through_to_heuristics(self) -> None:
        overrides = {"custom": ["legacy_*"]}
        assert classify_addon("Apik", "other", "", project_author="Apik", overrides=overrides) == "custom"
        assert classify_addon("Someone", "other", "", overrides=overrides) == "third-party"


class TestMatchClassification:
    def test_no_match_returns_none(self) -> None:
        assert match_classification("sale_x", {"custom": ["legacy_*"]}) is None

    def test_no_rules_returns_none(self) -> None:
        assert match_classification("sale_x", None) is None
        assert match_classification("sale_x", {}) is None

    def test_pattern_must_match_whole_name(self) -> None:
        # A bare prefix is an exact name, not a startswith: this is what keeps
        # a "sale" rule away from "sale_*" addons.
        assert match_classification("sale_management", {"custom": ["sale"]}) is None

    def test_glob_does_not_match_inside_name(self) -> None:
        assert match_classification("x_legacy_mail", {"custom": ["legacy_*"]}) is None

    def test_matching_is_case_sensitive(self) -> None:
        assert match_classification("legacy_mail", {"custom": ["LEGACY_*"]}) is None

    def test_exact_name_beats_glob_of_other_class(self) -> None:
        rules = {"custom": ["acme_*"], "third-party": ["acme_vendored"]}
        assert match_classification("acme_vendored", rules) == "third-party"
        assert match_classification("acme_sale", rules) == "custom"

    def test_two_globs_same_class_is_not_a_conflict(self) -> None:
        assert match_classification("acme_sale", {"custom": ["acme_*", "*_sale"]}) == "custom"

    def test_globs_of_two_classes_conflict(self) -> None:
        rules = {"custom": ["acme_*"], "third-party": ["*_sale"]}
        with pytest.raises(ClassificationConflict, match="acme_sale"):
            match_classification("acme_sale", rules)

    def test_exact_names_of_two_classes_conflict(self) -> None:
        rules = {"custom": ["sale_x"], "oca": ["sale_x"]}
        with pytest.raises(ClassificationConflict, match="sale_x"):
            match_classification("sale_x", rules)

    def test_conflict_only_raised_for_affected_addon(self) -> None:
        rules = {"custom": ["acme_*"], "third-party": ["*_sale"]}
        assert match_classification("acme_crm", rules) == "custom"
