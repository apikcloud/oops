"""Tests for oops/rules/manifest.py — direct visitor testing without fixit runner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import libcst as cst
import pytest

from oops.rules.manifest import (
    ManifestKeyOrder,
    ManifestNoExtraKeys,
    ManifestRequiredKeys,
    ManifestVersionBump,
    OdooManifestAuthorMaintainers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_dict(src: str) -> cst.Dict:
    """Parse a Python dict literal into a libcst Dict node."""
    return cst.parse_expression(src)  # type: ignore[return-value]


def make_rule(cls, **kwargs):
    """Instantiate a rule bypassing __init__ config loading.

    Passes a fresh *reports* list and patches ``report`` to append to it.
    Returns ``(rule, reports)``.
    """
    rule = cls.__new__(cls)
    rule._checked = False
    # Apply class-level defaults
    for attr, val in cls.__dict__.items():
        if not attr.startswith("_") and not callable(val) and not isinstance(val, classmethod):
            try:
                setattr(rule, attr, val)
            except (AttributeError, TypeError):
                pass

    reports = []

    def _report(node, message="", replacement=None):
        reports.append({"message": message, "replacement": replacement})

    rule.report = _report

    # Apply any overrides
    for k, v in kwargs.items():
        setattr(rule, k, v)

    return rule, reports


# ---------------------------------------------------------------------------
# ManifestRequiredKeys
# ---------------------------------------------------------------------------


class TestManifestRequiredKeys:
    FULL_MANIFEST = """{
        "name": "My Addon",
        "version": "16.0.1.0.0",
        "summary": "Does something.",
        "website": "https://example.com",
        "author": "Acme",
        "maintainers": ["alice"],
        "depends": [],
        "data": [],
        "license": "LGPL-3",
        "auto_install": False,
        "installable": True,
    }"""

    def test_no_violations_when_all_keys_present(self):
        rule, reports = make_rule(ManifestRequiredKeys)
        rule.visit_Dict(parse_dict(self.FULL_MANIFEST))
        assert reports == []

    def test_reports_missing_key(self):
        rule, reports = make_rule(ManifestRequiredKeys)
        d = parse_dict('{"name": "x"}')
        rule.visit_Dict(d)
        messages = [r["message"] for r in reports]
        assert any("version" in m for m in messages)

    def test_reports_all_missing_keys(self):
        rule, reports = make_rule(ManifestRequiredKeys)
        rule.visit_Dict(parse_dict('{"name": "x"}'))
        # All required keys except 'name' should be reported
        messages = " ".join(r["message"] for r in reports)
        for key in ["version", "author", "license"]:
            assert key in messages

    def test_guard_prevents_second_run(self):
        rule, reports = make_rule(ManifestRequiredKeys)
        d = parse_dict('{"name": "x"}')
        rule.visit_Dict(d)
        count_first = len(reports)
        rule.visit_Dict(d)
        assert len(reports) == count_first  # no extra reports

    def test_custom_required_keys(self):
        rule, reports = make_rule(ManifestRequiredKeys, required_keys=["name", "custom_key"])
        rule.visit_Dict(parse_dict('{"name": "x"}'))
        assert any("custom_key" in r["message"] for r in reports)
        assert not any("version" in r["message"] for r in reports)


# ---------------------------------------------------------------------------
# OdooManifestAuthorMaintainers
# ---------------------------------------------------------------------------


class TestCheckAuthor:
    def test_no_report_when_author_matches(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, expected_author="Acme")
        d = parse_dict('{"author": "Acme"}')
        rule._check_author({"author": d.elements[0].value})
        assert reports == []

    def test_reports_wrong_author(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, expected_author="Acme")
        d = parse_dict('{"author": "SomeoneElse"}')
        rule._check_author({"author": d.elements[0].value})
        assert len(reports) == 1
        assert "Acme" in reports[0]["message"]

    def test_autofix_preserves_quote_style(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, expected_author="Acme")
        d = parse_dict("{'author': 'Wrong'}")
        rule._check_author({"author": d.elements[0].value})
        assert reports[0]["replacement"] is not None
        assert reports[0]["replacement"].value.startswith("'")

    def test_skipped_when_no_expected_author(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, expected_author="")
        d = parse_dict('{"author": "anyone"}')
        rule._check_author({"author": d.elements[0].value})
        assert reports == []

    def test_skipped_when_key_absent(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, expected_author="Acme")
        rule._check_author({})
        assert reports == []


class TestCheckMaintainers:
    def _get_value(self, src: str, key: str) -> cst.BaseExpression:
        d = parse_dict(src)
        from oops.rules._helpers import extract_kv
        return extract_kv(d)[key]

    def test_no_report_when_absent(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, allowed_maintainers=[])
        rule._check_maintainers({})
        assert reports == []

    def test_reports_not_a_list(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, allowed_maintainers=[])
        d = parse_dict('{"maintainers": "alice"}')
        from oops.rules._helpers import extract_kv
        rule._check_maintainers(extract_kv(d))
        assert any("must be a list" in r["message"] for r in reports)

    def test_reports_empty_list(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, allowed_maintainers=[])
        d = parse_dict('{"maintainers": []}')
        from oops.rules._helpers import extract_kv
        rule._check_maintainers(extract_kv(d))
        assert any("must not be empty" in r["message"] for r in reports)

    def test_reports_unknown_maintainer(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, allowed_maintainers=["alice"])
        d = parse_dict('{"maintainers": ["bob"]}')
        from oops.rules._helpers import extract_kv
        rule._check_maintainers(extract_kv(d))
        assert any("not in the allowed list" in r["message"] for r in reports)

    def test_no_report_when_allowed_list_empty(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, allowed_maintainers=[])
        d = parse_dict('{"maintainers": ["anyone"]}')
        from oops.rules._helpers import extract_kv
        rule._check_maintainers(extract_kv(d))
        assert reports == []

    def test_no_report_when_maintainer_valid(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, allowed_maintainers=["alice"])
        d = parse_dict('{"maintainers": ["alice"]}')
        from oops.rules._helpers import extract_kv
        rule._check_maintainers(extract_kv(d))
        assert reports == []


class TestCheckSummary:
    def test_no_report_when_absent(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers)
        rule._check_summary({})
        assert reports == []

    def test_reports_empty_summary(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers)
        d = parse_dict('{"summary": "   "}')
        from oops.rules._helpers import extract_kv
        rule._check_summary(extract_kv(d))
        assert any("must not be empty" in r["message"] for r in reports)

    def test_reports_summary_equals_name(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers)
        d = parse_dict('{"name": "My Addon", "summary": "My Addon"}')
        from oops.rules._helpers import extract_kv
        rule._check_summary(extract_kv(d))
        assert any("must differ" in r["message"] for r in reports)

    def test_no_report_valid_summary(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers)
        d = parse_dict('{"name": "My Addon", "summary": "Manages invoices."}')
        from oops.rules._helpers import extract_kv
        rule._check_summary(extract_kv(d))
        assert reports == []


class TestCheckVersion:
    def test_no_report_when_absent(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, odoo_version=None)
        rule._check_version({})
        assert reports == []

    def test_valid_generic_version_no_report(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, odoo_version=None)
        d = parse_dict('{"version": "16.0.1.0.0"}')
        from oops.rules._helpers import extract_kv
        rule._check_version(extract_kv(d))
        assert reports == []

    def test_valid_odoo_version_specific_no_report(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, odoo_version="19.0")
        d = parse_dict('{"version": "19.0.1.0.0"}')
        from oops.rules._helpers import extract_kv
        rule._check_version(extract_kv(d))
        assert reports == []

    def test_reports_wrong_prefix(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, odoo_version="19.0")
        d = parse_dict('{"version": "18.0.1.0.0"}')
        from oops.rules._helpers import extract_kv
        rule._check_version(extract_kv(d))
        assert len(reports) == 1
        assert "19.0" in reports[0]["message"]

    def test_autofix_typo_O_to_0(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, odoo_version=None)
        d = parse_dict('{"version": "16.0.1.0.O"}')
        from oops.rules._helpers import extract_kv
        rule._check_version(extract_kv(d))
        assert len(reports) == 1
        assert reports[0]["replacement"] is not None
        assert "16.0.1.0.0" in reports[0]["replacement"].value

    def test_autofix_typo_l_to_1(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, odoo_version=None)
        d = parse_dict('{"version": "l6.0.1.0.0"}')
        from oops.rules._helpers import extract_kv
        rule._check_version(extract_kv(d))
        assert reports[0]["replacement"] is not None

    def test_no_autofix_when_corrected_still_invalid(self):
        rule, reports = make_rule(OdooManifestAuthorMaintainers, odoo_version=None)
        d = parse_dict('{"version": "totally_wrong"}')
        from oops.rules._helpers import extract_kv
        rule._check_version(extract_kv(d))
        assert reports[0]["replacement"] is None

    def test_visit_Dict_calls_all_checks(self):
        rule, reports = make_rule(
            OdooManifestAuthorMaintainers,
            expected_author="Acme",
            odoo_version="19.0",
            allowed_maintainers=["alice"],
        )
        d = parse_dict(
            '{"author": "Wrong", "maintainers": [], "summary": "", "version": "bad"}'
        )
        rule.visit_Dict(d)
        messages = " ".join(r["message"] for r in reports)
        assert "author" in messages.lower()


# ---------------------------------------------------------------------------
# ManifestNoExtraKeys
# ---------------------------------------------------------------------------


class TestManifestNoExtraKeys:
    def test_no_report_for_allowed_keys(self):
        rule, reports = make_rule(ManifestNoExtraKeys)
        d = parse_dict('{"name": "x", "version": "1.0"}')
        rule.visit_Dict(d)
        assert reports == []

    def test_reports_unknown_key(self):
        rule, reports = make_rule(ManifestNoExtraKeys, allowed_keys=["name", "version"])
        d = parse_dict('{"name": "x", "debug_flag": True}')
        rule.visit_Dict(d)
        assert any("debug_flag" in r["message"] for r in reports)

    def test_guard_prevents_second_run(self):
        rule, reports = make_rule(ManifestNoExtraKeys, allowed_keys=["name"])
        d = parse_dict('{"name": "x", "extra": 1}')
        rule.visit_Dict(d)
        count = len(reports)
        rule.visit_Dict(d)
        assert len(reports) == count


# ---------------------------------------------------------------------------
# ManifestKeyOrder
# ---------------------------------------------------------------------------


class TestManifestKeyOrder:
    ORDER = ["name", "version", "author", "license"]

    def test_no_report_when_already_sorted(self):
        rule, reports = make_rule(ManifestKeyOrder, key_order=self.ORDER)
        d = parse_dict('{"name": "x", "version": "1.0", "author": "a", "license": "LGPL-3"}')
        rule.visit_Dict(d)
        assert reports == []

    def test_reports_wrong_order(self):
        rule, reports = make_rule(ManifestKeyOrder, key_order=self.ORDER)
        d = parse_dict('{"author": "a", "name": "x"}')
        rule.visit_Dict(d)
        assert len(reports) == 1
        assert "order" in reports[0]["message"].lower()

    def test_autofix_provides_replacement(self):
        rule, reports = make_rule(ManifestKeyOrder, key_order=self.ORDER)
        d = parse_dict('{"license": "LGPL-3", "name": "x"}')
        rule.visit_Dict(d)
        assert reports[0]["replacement"] is not None

    def test_empty_dict_no_report(self):
        rule, reports = make_rule(ManifestKeyOrder, key_order=self.ORDER)
        d = parse_dict("{}")
        rule.visit_Dict(d)
        assert reports == []

    def test_sorted_order_produces_correct_keys(self):
        from oops.rules._helpers import key_name

        rule, reports = make_rule(ManifestKeyOrder, key_order=self.ORDER)
        d = parse_dict('{"license": "LGPL-3", "version": "1.0", "name": "x", "author": "a"}')
        rule.visit_Dict(d)
        replacement = reports[0]["replacement"]
        result_keys = [key_name(e) for e in replacement.elements if isinstance(e, cst.DictElement)]
        assert result_keys == ["name", "version", "author", "license"]

    def test_unknown_keys_pushed_to_end(self):
        from oops.rules._helpers import key_name

        rule, reports = make_rule(ManifestKeyOrder, key_order=["name", "version"])
        d = parse_dict('{"zzz": 1, "version": "1.0", "name": "x"}')
        rule.visit_Dict(d)
        replacement = reports[0]["replacement"]
        result_keys = [key_name(e) for e in replacement.elements if isinstance(e, cst.DictElement)]
        assert result_keys[0] == "name"
        assert result_keys[1] == "version"
        assert result_keys[2] == "zzz"


# ---------------------------------------------------------------------------
# ManifestVersionBump
# ---------------------------------------------------------------------------


class TestManifestVersionBump:
    def _make_bump_rule(self, strategy="off", ref_version=None, path=None):
        """Create a ManifestVersionBump with injected state (bypassing __init__)."""
        rule = ManifestVersionBump.__new__(ManifestVersionBump)
        rule._checked = False
        rule.version_bump_strategy = strategy
        rule._ref_version = ref_version

        reports = []

        def _report(node, message="", replacement=None):
            reports.append({"message": message})

        rule.report = _report
        return rule, reports

    def test_disabled_when_strategy_off(self):
        rule, reports = self._make_bump_rule(strategy="off", ref_version=None)
        d = parse_dict('{"version": "16.0.1.0.0"}')
        rule.visit_Dict(d)
        assert reports == []

    def test_no_report_when_ref_version_is_none(self):
        rule, reports = self._make_bump_rule(strategy="strict", ref_version=None)
        d = parse_dict('{"version": "16.0.1.0.0"}')
        rule.visit_Dict(d)
        assert reports == []

    def test_reports_when_version_not_bumped(self):
        rule, reports = self._make_bump_rule(
            strategy="strict", ref_version=(16, 0, 1, 0, 0)
        )
        d = parse_dict('{"version": "16.0.1.0.0"}')
        rule.visit_Dict(d)
        assert len(reports) == 1
        assert "not bumped" in reports[0]["message"]

    def test_no_report_when_version_bumped(self):
        rule, reports = self._make_bump_rule(
            strategy="strict", ref_version=(16, 0, 1, 0, 0)
        )
        d = parse_dict('{"version": "16.0.1.0.1"}')
        rule.visit_Dict(d)
        assert reports == []

    def test_guard_prevents_second_run(self):
        rule, reports = self._make_bump_rule(
            strategy="strict", ref_version=(16, 0, 1, 0, 0)
        )
        d = parse_dict('{"version": "16.0.1.0.0"}')
        rule.visit_Dict(d)
        count = len(reports)
        rule.visit_Dict(d)
        assert len(reports) == count

    def test_no_report_when_version_absent(self):
        rule, reports = self._make_bump_rule(
            strategy="strict", ref_version=(16, 0, 1, 0, 0)
        )
        d = parse_dict('{"name": "x"}')
        rule.visit_Dict(d)
        assert reports == []

    def test_init_disabled_when_strategy_off(self):
        """__init__ with strategy=off should not set _ref_version."""
        with patch("oops.rules.manifest._load_manifest_cfg") as mock_cfg:
            cfg_mock = MagicMock()
            cfg_mock.version_bump_strategy = "off"
            mock_cfg.return_value = cfg_mock
            rule = ManifestVersionBump()
            assert rule._ref_version is None

    def test_init_disabled_when_no_config(self):
        """__init__ with no config should leave rule inactive."""
        with patch("oops.rules.manifest._load_manifest_cfg", return_value=None):
            rule = ManifestVersionBump()
            assert rule._ref_version is None

    def test_init_disabled_when_path_not_set(self):
        """__init__ should return early if lint path is not set."""
        with (
            patch("oops.rules.manifest._load_manifest_cfg") as mock_cfg,
            patch("oops.rules.manifest._get_lint_path", return_value=None),
        ):
            cfg_mock = MagicMock()
            cfg_mock.version_bump_strategy = "strict"
            mock_cfg.return_value = cfg_mock
            rule = ManifestVersionBump()
            assert rule._ref_version is None

    def test_init_strict_with_staged_manifest(self, tmp_path):
        """__init__ with strict strategy and staged manifest sets _ref_version."""
        manifest_path = tmp_path / "my_addon" / "__manifest__.py"
        manifest_path.parent.mkdir()
        manifest_path.write_text('{"version": "16.0.1.0.0"}')
        rel_path = "my_addon/__manifest__.py"

        with (
            patch("oops.rules.manifest._load_manifest_cfg") as mock_cfg,
            patch("oops.rules.manifest._get_lint_path", return_value=manifest_path),
            patch("oops.rules.manifest._git_repo_root", return_value=tmp_path),
            patch(
                "oops.rules.manifest._staged_addon_manifest_relpaths",
                return_value=frozenset({rel_path}),
            ),
            patch(
                "oops.rules.manifest._file_at_ref",
                return_value='{"version": "16.0.1.0.0"}',
            ),
        ):
            cfg_mock = MagicMock()
            cfg_mock.version_bump_strategy = "strict"
            mock_cfg.return_value = cfg_mock
            rule = ManifestVersionBump()
            assert rule._ref_version == (16, 0, 1, 0, 0)

    def test_init_trunk_no_tag_disables_rule(self):
        """__init__ with trunk strategy and no tag leaves rule inactive."""
        with (
            patch("oops.rules.manifest._load_manifest_cfg") as mock_cfg,
            patch("oops.rules.manifest._last_tag", return_value=None),
        ):
            cfg_mock = MagicMock()
            cfg_mock.version_bump_strategy = "trunk"
            mock_cfg.return_value = cfg_mock
            rule = ManifestVersionBump()
            assert rule._ref_version is None

    def test_reports_version_not_bumped_with_strategy_in_message(self):
        """version_bump_strategy string is included in report message."""
        rule, reports = self._make_bump_rule(
            strategy="trunk", ref_version=(16, 0, 1, 0, 0)
        )
        d = parse_dict('{"version": "16.0.1.0.0"}')
        rule.visit_Dict(d)
        assert "trunk" in reports[0]["message"]

    def test_no_report_when_val_is_none(self):
        """Non-string version_node (val=None) silently returns."""
        rule, reports = self._make_bump_rule(
            strategy="strict", ref_version=(16, 0, 1, 0, 0)
        )
        # Use a dict where the version value is not a SimpleString
        d = cst.parse_expression('{"version": some_var}')
        rule.visit_Dict(d)  # type: ignore[arg-type]
        assert reports == []

    def test_no_report_when_version_unparseable(self):
        """Non-numeric version string triggers ValueError, rule skips silently."""
        rule, reports = self._make_bump_rule(
            strategy="strict", ref_version=(16, 0, 1, 0, 0)
        )
        d = parse_dict('{"version": "abc.def.ghi"}')
        rule.visit_Dict(d)
        assert reports == []


# ---------------------------------------------------------------------------
# Rule __init__ instantiation coverage (runs through config-loading paths)
# ---------------------------------------------------------------------------


class TestRuleInitWithConfig:
    """Instantiate each rule normally to exercise the __init__ config-loading branches."""

    def test_manifest_required_keys_init(self):
        rule = ManifestRequiredKeys()
        assert isinstance(rule.required_keys, list)

    def test_odoo_manifest_author_maintainers_init(self):
        rule = OdooManifestAuthorMaintainers()
        assert isinstance(rule.allowed_maintainers, list)

    def test_manifest_no_extra_keys_init(self):
        rule = ManifestNoExtraKeys()
        assert isinstance(rule.allowed_keys, list)

    def test_manifest_key_order_init(self):
        rule = ManifestKeyOrder()
        assert isinstance(rule.key_order, list)

    def test_guard_in_odoo_manifest_author_maintainers(self):
        """Second call to visit_Dict should be a no-op (guard check)."""
        rule = OdooManifestAuthorMaintainers()
        reports = []
        rule.report = lambda node, message="", replacement=None: reports.append(message)
        d = parse_dict('{"name": "x"}')
        rule.visit_Dict(d)
        count_first = len(reports)
        rule.visit_Dict(d)
        assert len(reports) == count_first

    def test_guard_in_manifest_no_extra_keys(self):
        """Second call to visit_Dict should be a no-op."""
        rule = ManifestNoExtraKeys()
        reports = []
        rule.report = lambda node, message="", replacement=None: reports.append(message)
        d = parse_dict('{"name": "x", "unknown_key": 1}')
        rule.visit_Dict(d)
        count_first = len(reports)
        rule.visit_Dict(d)
        assert len(reports) == count_first
