"""Tests for the three problematic-requirements detection functions.

Functions under test (src/oops/io/requirements.py):
    - get_requirements_with_unsupported_operator
    - get_requirements_with_conflicting_exact_pins
    - get_requirements_with_contradictory_range
"""

from oops.io.requirements import (
    _gather_repository_requirements,
    get_requirements_with_conflicting_exact_pins,
    get_requirements_with_contradictory_range,
    get_requirements_with_unsupported_operator,
)
from tests.helpers import make_addon as _make_addon
from tests.helpers import patch_requirements_addons as _patch_addons


def _run_check(check_func, repository_path):
    """Helper to gather requirements from repository and execute the given check function."""
    all_constraints, constraint_to_addons, _, _ = _gather_repository_requirements(
        repository_path, allow_not_equal_operator=True
    )
    return check_func(all_constraints, constraint_to_addons)


# ---------------------------------------------------------------------------
# get_requirements_with_unsupported_operator
# ---------------------------------------------------------------------------
class TestGetRequirementsWithUnsupportedOperator:
    def test_no_issues_when_no_addons(self, tmp_path, monkeypatch):
        _patch_addons(monkeypatch, [])
        result = _run_check(get_requirements_with_unsupported_operator, tmp_path)
        assert result == []

    def test_no_issues_for_clean_deps(self, tmp_path, monkeypatch):
        _patch_addons(monkeypatch, [_make_addon("mod_a", ["requests>=2.0", "lxml"])])
        result = _run_check(get_requirements_with_unsupported_operator, tmp_path)
        assert result == []

    def test_detects_neq_operator(self, tmp_path, monkeypatch):
        _patch_addons(monkeypatch, [_make_addon("mod_a", ["requests!=2.0"])])
        result = _run_check(get_requirements_with_unsupported_operator, tmp_path)
        assert result == ["mod_a: requests!=2.0"]

    def test_detects_multiple_neq_from_same_addon(self, tmp_path, monkeypatch):
        _patch_addons(monkeypatch, [_make_addon("mod_a", ["requests!=2.0", "lxml!=4.0"])])
        result = _run_check(get_requirements_with_unsupported_operator, tmp_path)
        assert "mod_a: lxml!=4.0" in result
        assert "mod_a: requests!=2.0" in result

    def test_detects_neq_from_multiple_addons(self, tmp_path, monkeypatch):
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["requests!=2.0"]),
                _make_addon("mod_b", ["requests!=2.0"]),
            ],
        )
        result = _run_check(get_requirements_with_unsupported_operator, tmp_path)
        assert "mod_a: requests!=2.0" in result
        assert "mod_b: requests!=2.0" in result

    def test_supported_operators_not_flagged(self, tmp_path, monkeypatch):
        _patch_addons(
            monkeypatch,
            [_make_addon("mod_a", ["requests>=2.0", "requests<=3.0", "lxml>1.0", "lxml<5.0"])],
        )
        result = _run_check(get_requirements_with_unsupported_operator, tmp_path)
        assert result == []

    def test_output_format_is_addon_colon_constraint(self, tmp_path, monkeypatch):
        _patch_addons(monkeypatch, [_make_addon("my_module", ["pandas!=1.5"])])
        result = _run_check(get_requirements_with_unsupported_operator, tmp_path)
        assert len(result) == 1
        assert result[0] == "my_module: pandas!=1.5"


# ---------------------------------------------------------------------------
# get_requirements_with_conflicting_exact_pins
# ---------------------------------------------------------------------------
class TestGetRequirementsWithConflictingExactPins:
    def test_no_issues_when_no_addons(self, tmp_path, monkeypatch):
        _patch_addons(monkeypatch, [])
        result = _run_check(get_requirements_with_conflicting_exact_pins, tmp_path)
        assert result == []

    def test_no_issues_single_equal_pin(self, tmp_path, monkeypatch):
        _patch_addons(monkeypatch, [_make_addon("mod_a", ["requests==2.28.0"])])
        result = _run_check(get_requirements_with_conflicting_exact_pins, tmp_path)
        assert result == []

    def test_no_issues_same_pin_from_two_addons(self, tmp_path, monkeypatch):
        """Same version pinned by two addons is not a conflict."""
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["requests==2.28.0"]),
                _make_addon("mod_b", ["requests==2.28.0"]),
            ],
        )
        result = _run_check(get_requirements_with_conflicting_exact_pins, tmp_path)
        assert result == []

    def test_detects_conflicting_equal_pins(self, tmp_path, monkeypatch):
        """Two addons pin the same package to different versions."""
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["pandas==1.2.0"]),
                _make_addon("mod_b", ["pandas==1.3.0"]),
            ],
        )
        result = _run_check(get_requirements_with_conflicting_exact_pins, tmp_path)
        assert "mod_a: pandas==1.2.0" in result
        assert "mod_b: pandas==1.3.0" in result

    def test_detects_three_conflicting_pins(self, tmp_path, monkeypatch):
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["scipy==1.0.0"]),
                _make_addon("mod_b", ["scipy==1.1.0"]),
                _make_addon("mod_c", ["scipy==1.2.0"]),
            ],
        )
        result = _run_check(get_requirements_with_conflicting_exact_pins, tmp_path)
        assert "mod_a: scipy==1.0.0" in result
        assert "mod_b: scipy==1.1.0" in result
        assert "mod_c: scipy==1.2.0" in result

    def test_range_constraints_not_flagged(self, tmp_path, monkeypatch):
        """Range constraints (>=, <=) do not trigger exact-pin detection."""
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["requests>=2.0"]),
                _make_addon("mod_b", ["requests>=3.0"]),
            ],
        )
        result = _run_check(get_requirements_with_conflicting_exact_pins, tmp_path)
        assert result == []

    def test_output_format_is_addon_colon_constraint(self, tmp_path, monkeypatch):
        _patch_addons(
            monkeypatch,
            [
                _make_addon("alpha", ["lxml==4.9.0"]),
                _make_addon("beta", ["lxml==4.8.0"]),
            ],
        )
        result = _run_check(get_requirements_with_conflicting_exact_pins, tmp_path)
        for item in result:
            addon, _, constraint = item.partition(": ")
            assert addon in {"alpha", "beta"}
            assert constraint.startswith("lxml==")


# ---------------------------------------------------------------------------
# get_requirements_with_contradictory_range
# ---------------------------------------------------------------------------
class TestGetRequirementsWithContradictoryRange:
    def test_no_issues_when_no_addons(self, tmp_path, monkeypatch):
        _patch_addons(monkeypatch, [])
        result = _run_check(get_requirements_with_contradictory_range, tmp_path)
        assert result == []

    def test_no_issues_valid_range(self, tmp_path, monkeypatch):
        """Lower bound below upper bound — no contradiction."""
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["requests>=1.0"]),
                _make_addon("mod_b", ["requests<3.0"]),
            ],
        )
        result = _run_check(get_requirements_with_contradictory_range, tmp_path)
        assert result == []

    def test_detects_inverted_range(self, tmp_path, monkeypatch):
        """Lower bound greater than upper bound -> contradiction."""
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["pandas>2.0"]),
                _make_addon("mod_b", ["pandas<1.0"]),
            ],
        )
        result = _run_check(get_requirements_with_contradictory_range, tmp_path)
        assert any("mod_a" in item and "pandas>2.0" in item for item in result)
        assert any("mod_b" in item and "pandas<1.0" in item for item in result)

    def test_detects_equal_bounds(self, tmp_path, monkeypatch):
        """lower >= upper (equal strict bounds) is also contradictory."""
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["scipy>=2.0"]),
                _make_addon("mod_b", ["scipy<=2.0"]),
            ],
        )
        result = _run_check(get_requirements_with_contradictory_range, tmp_path)
        assert any("mod_a" in item and "scipy>=2.0" in item for item in result)
        assert any("mod_b" in item and "scipy<=2.0" in item for item in result)

    def test_no_false_positive_for_single_bound(self, tmp_path, monkeypatch):
        """A single floor or ceil alone cannot be contradictory."""
        _patch_addons(monkeypatch, [_make_addon("mod_a", ["requests>=1.0"])])
        result = _run_check(get_requirements_with_contradictory_range, tmp_path)
        assert result == []

    def test_equal_pin_not_treated_as_range(self, tmp_path, monkeypatch):
        """== pins are excluded from range-contradiction detection."""
        _patch_addons(
            monkeypatch,
            [
                _make_addon("mod_a", ["requests==2.0"]),
                _make_addon("mod_b", ["requests==1.0"]),
            ],
        )
        result = _run_check(get_requirements_with_contradictory_range, tmp_path)
        assert result == []

    def test_output_format_is_addon_colon_constraint(self, tmp_path, monkeypatch):
        _patch_addons(
            monkeypatch,
            [
                _make_addon("module_x", ["numpy>5.0"]),
                _make_addon("module_y", ["numpy<2.0"]),
            ],
        )
        result = _run_check(get_requirements_with_contradictory_range, tmp_path)
        for item in result:
            addon, sep, constraint = item.partition(": ")
            assert sep == ": "
            assert addon in {"module_x", "module_y"}
            assert constraint.startswith("numpy")
