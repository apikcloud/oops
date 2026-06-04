# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_kb_identity.py — tests/test_kb_identity.py

"""Tests for oops/kb/identity.py — id builders and source-path normalization."""

from __future__ import annotations

from oops.kb.identity import field_id, method_id, model_id, normalize_source_file


def test_model_id() -> None:
    assert model_id("project_management", "project.project") == "project_management:project.project"


def test_field_id() -> None:
    assert (
        field_id("project_management", "project.project", "dev_hours")
        == "project_management:project.project#field:dev_hours"
    )


def test_method_id() -> None:
    assert (
        method_id("project_management", "project.project", "_compute_dev_hours")
        == "project_management:project.project#method:_compute_dev_hours"
    )


def test_normalize_source_file_trims_deep_prefix() -> None:
    assert (
        normalize_source_file("org/repo/project_management/views/x.xml", "project_management")
        == "project_management/views/x.xml"
    )


def test_normalize_source_file_already_rooted_is_idempotent() -> None:
    rooted = "project_management/models/project_project.py"
    assert normalize_source_file(rooted, "project_management") == rooted
    # idempotence
    assert normalize_source_file(normalize_source_file(rooted, "project_management"), "project_management") == rooted


def test_normalize_source_file_uses_last_module_segment() -> None:
    # A parent dir sharing the module name must not cause an early cut.
    assert (
        normalize_source_file("a/my_module/b/my_module/models/x.py", "my_module")
        == "my_module/models/x.py"
    )


def test_normalize_source_file_passthrough_when_module_absent() -> None:
    assert normalize_source_file("some/other/path.py", "my_module") == "some/other/path.py"


def test_normalize_source_file_handles_none_and_empty() -> None:
    assert normalize_source_file(None, "m") is None
    assert normalize_source_file("", "m") == ""


def test_normalize_source_file_backslashes() -> None:
    assert (
        normalize_source_file("org\\repo\\my_module\\views\\x.xml", "my_module")
        == "my_module/views/x.xml"
    )
