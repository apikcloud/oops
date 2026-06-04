# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_kb_provenance.py — tests/test_kb_provenance.py

"""Tests for oops/kb/provenance.py — the unified origin vocabulary."""

from __future__ import annotations

import pytest
from oops.kb.provenance import (
    ORIGIN_CORE,
    ORIGIN_CUSTOM,
    ORIGIN_ENTERPRISE,
    ORIGIN_OCA,
    ORIGIN_THIRD_PARTY,
    ORIGINS,
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
        ("community", ORIGIN_CORE),
        ("themes", ORIGIN_CORE),
        ("enterprise", ORIGIN_ENTERPRISE),
        ("third-party", ORIGIN_THIRD_PARTY),
        ("third_party", ORIGIN_THIRD_PARTY),
        ("apik", ORIGIN_CUSTOM),
        ("local", ORIGIN_CUSTOM),
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


def test_no_legacy_string_leaks() -> None:
    # The mapper must never emit a legacy variant.
    for raw in ("odoo", "third-party", "community"):
        assert normalize_origin(raw) not in {"odoo", "third-party", "community"}
