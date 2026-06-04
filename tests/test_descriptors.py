# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_descriptors.py — tests/test_descriptors.py

"""Tests for the analyze IR v2 descriptor registry and its loader."""

from __future__ import annotations

from oops.output.descriptors import descriptor, kind_of, label_of, load_descriptors, schema_version


def test_registry_is_valid_and_versioned() -> None:
    reg = load_descriptors()
    assert reg["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert reg["x-schema-version"] == 2
    assert schema_version() == 2
    assert set(reg["definitions"]) == {"metrics", "loc", "manifest"}


def test_every_descriptor_has_title_and_kind() -> None:
    reg = load_descriptors()
    for group in ("metrics", "loc", "manifest"):
        props = reg["definitions"][group]["properties"]
        assert props, f"{group} has no descriptors"
        for key, d in props.items():
            assert d.get("title"), f"{group}.{key} missing title"
            assert d.get("x-kind"), f"{group}.{key} missing x-kind"
            assert "x-unit" in d, f"{group}.{key} missing x-unit"


def test_label_and_kind_lookup() -> None:
    assert label_of("metrics", "own_fields") == "Fields (own)"
    assert kind_of("loc", "pct") == "percent"
    assert kind_of("metrics", "models") == "count"


def test_lookup_fallbacks_for_unknown_key() -> None:
    assert descriptor("metrics", "nope") is None
    assert label_of("metrics", "nope", "Default") == "Default"
    assert kind_of("metrics", "nope", "text") == "text"
