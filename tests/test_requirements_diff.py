"""Tests for get_requirements_diff in oops/io/file.py.

The function compares the python deps declared in addon manifests
against the current requirements.txt, and returns what should change.
"""

import textwrap
from pathlib import Path

import pytest
from oops.core.models import AddonInfo
from oops.io.file import get_requirements_diff

# The comment line that is always written at the top of the generated file.
HEADER = "# generated from manifests external_dependencies"


# ---------------------------------------------------------------------------
# Helpers — build fake addons without touching the filesystem
# ---------------------------------------------------------------------------


def _make_addon(technical_name: str, python_deps: list) -> AddonInfo:
    """Minimal AddonInfo with only the python external_dependencies filled in."""
    return AddonInfo(
        path=f"/fake/{technical_name}",
        rel_path="",
        technical_name=technical_name,
        symlink=False,
        root=True,
        version="16.0.1.0.0",
        author="Apik",
        maintainers=[],
        summary="",
        external_dependencies={"python": python_deps},
        depends=[],
        installable=True,
    )


def _make_addon_full_deps(technical_name: str, external_dependencies: dict) -> AddonInfo:
    """Minimal AddonInfo where the full external_dependencies dict is provided.

    Use this when you need to test non-python keys (e.g. 'bin') or an empty dict.
    """
    return AddonInfo(
        path=f"/fake/{technical_name}",
        rel_path="",
        technical_name=technical_name,
        symlink=False,
        root=True,
        version="16.0.1.0.0",
        author="Apik",
        maintainers=[],
        summary="",
        external_dependencies=external_dependencies,
        depends=[],
        installable=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetRequirementsDiff:
    def _patch_addons(self, monkeypatch, addons: list):
        """Replace find_addons() so we control exactly which addons are scanned."""
        monkeypatch.setattr("oops.io.file.find_addons", lambda *a, **kw: iter(addons))

    def _write_reqs(self, tmp_path: Path, content: str = "") -> None:
        """Write (or overwrite) requirements.txt in the fake repo root."""
        (tmp_path / "requirements.txt").write_text(content)

    def test_no_addons_no_changes(self, tmp_path, monkeypatch):
        """Returns (bool, list, list) with no changes and header-only output when the project is empty."""
        self._write_reqs(tmp_path)
        self._patch_addons(monkeypatch, [])

        has_changes, new_lines, diff = get_requirements_diff(tmp_path)

        assert isinstance(has_changes, bool)
        assert isinstance(new_lines, list)
        assert isinstance(diff, list)
        assert has_changes is False
        assert new_lines == [HEADER]
        assert diff == []

    def test_has_changes_flag(self, tmp_path, monkeypatch):
        """Signals whether requirements.txt is out of sync with the manifests."""
        cases = {
            # requirements.txt already matches the manifests → nothing to do
            "in sync": ("requests\n", ["requests"], False),
            # the generated header comment must be ignored when comparing
            "comment header ignored": (
                "# generated from manifests external_dependencies\nrequests\n",
                ["requests"],
                False,
            ),
            # a dep present in the manifests but missing from the file
            "manifest adds dep": ("requests\n", ["requests", "lxml"], True),
            # a dep present in the file but no longer declared in any manifest
            "file has extra dep": ("requests\nold-package\n", ["requests"], True),
            # requirements.txt is read with unique=False, so duplicates count as a diff
            "duplicate in file": ("requests\nrequests\n", ["requests"], True),
        }
        for description, (reqs_content, python_deps, expected) in cases.items():
            self._write_reqs(tmp_path, reqs_content)
            self._patch_addons(monkeypatch, [_make_addon("a", python_deps)])

            has_changes, _, _ = get_requirements_diff(tmp_path)

            assert has_changes is expected, description

    def test_name_mapping(self, tmp_path, monkeypatch):
        """Translates import names to their pip package names before writing the output."""
        cases = {
            # well-known import-name → pip-name translations
            "PIL → Pillow": ("PIL", "Pillow"),
            "dateutil → python-dateutil": ("dateutil", "python-dateutil"),
            "stdnum → python-stdnum": ("stdnum", "python-stdnum"),
            "shopify → ShopifyAPI": ("shopify", "ShopifyAPI"),
            # a name not in the mapping should be kept as-is
            "unknown name passes through": ("boto3", "boto3"),
            # the mapping must also work when a version constraint is attached
            "mapping applied with version": ("PIL>=9.0", "Pillow>=9.0"),
        }
        for description, (input_dep, expected) in cases.items():
            self._write_reqs(tmp_path)
            self._patch_addons(monkeypatch, [_make_addon("a", [input_dep])])

            _, new_lines, _ = get_requirements_diff(tmp_path)

            assert expected in new_lines, description
            if input_dep != expected:
                # the original import name must not leak into the output
                assert input_dep not in new_lines, description

    def test_single_version_constraint(self, tmp_path, monkeypatch):
        """Preserves a single version constraint (floor or ceil) exactly as declared."""
        cases = {
            ">= floor": "requests>=2.0",
            ">  floor": "requests>2.0",
            "<  ceil": "requests<3.0",
            "<= ceil": "requests<=3.0",
        }
        for description, dep in cases.items():
            self._write_reqs(tmp_path)
            self._patch_addons(monkeypatch, [_make_addon("a", [dep])])

            _, new_lines, _ = get_requirements_diff(tmp_path)

            assert dep in new_lines, description

    def test_version_constraint_merging(self, tmp_path, monkeypatch):
        """Merges constraints from multiple addons into the tightest range: highest floor + lowest ceil."""
        cases = {
            # one addon brings the floor, another brings the ceil → single range
            "floor + ceil merged": (
                [["requests>=2.0"], ["requests<3.0"]],
                "requests>=2.0,<3.0",
                ["requests>=2.0", "requests<3.0"],
            ),
            # two different floors → keep the highest one (most restrictive)
            "highest floor wins": (
                [["requests>=1.0"], ["requests>=2.0"]],
                "requests>=2.0",
                ["requests>=1.0"],
            ),
            # two different ceils → keep the lowest one (most restrictive)
            "lowest ceil wins": (
                [["requests<3.0"], ["requests<2.0"]],
                "requests<2.0",
                ["requests<3.0"],
            ),
        }
        for description, (addons_deps, expected_in, expected_not_in) in cases.items():
            self._write_reqs(tmp_path)
            addons = [_make_addon(str(i), deps) for i, deps in enumerate(addons_deps)]
            self._patch_addons(monkeypatch, addons)

            _, new_lines, _ = get_requirements_diff(tmp_path)

            assert expected_in in new_lines, description
            for dep in expected_not_in:
                assert dep not in new_lines, description

    def test_equality_pin_preserved(self, tmp_path, monkeypatch):
        """Passes == pins through as-is without arbitration, even alongside range constraints."""
        cases = {
            # a plain == pin must not be silently stripped to a bare name
            "single == pin": ([["requests==2.0"]], ["requests==2.0"], ["requests"]),
            # == coexists with a range from another addon → both appear, human decides
            "== coexists with range, both kept": (
                [["requests==2.0"], ["requests>=1.0"]],
                ["requests==2.0", "requests>=1.0"],
                [],
            ),
            # same == from two addons → deduplicated to one entry (set behaviour)
            "duplicate == across addons, kept once": ([["requests==2.0"], ["requests==2.0"]], ["requests==2.0"], []),
        }
        for description, (addons_deps, expected_in, expected_not_in) in cases.items():
            self._write_reqs(tmp_path)
            addons = [_make_addon(str(i), deps) for i, deps in enumerate(addons_deps)]
            self._patch_addons(monkeypatch, addons)

            _, new_lines, _ = get_requirements_diff(tmp_path)

            for item in expected_in:
                assert item in new_lines, f"{description}: {item!r} missing"
            for item in expected_not_in:
                assert item not in new_lines, f"{description}: {item!r} should not be present"

    def test_strict_operator_wins_over_nonstrict_at_same_version(self, tmp_path, monkeypatch):
        """When > and >= appear for the same version, the strict operator wins."""
        self._write_reqs(tmp_path)
        addons = [
            _make_addon("a", ["requests>1.0"]),
            _make_addon("b", ["requests>=1.0"]),
        ]
        self._patch_addons(monkeypatch, addons)

        _, new_lines, _ = get_requirements_diff(tmp_path)

        assert "requests>1.0" in new_lines
        assert "requests>=1.0" not in new_lines

    def test_output_structure(self, tmp_path, monkeypatch):
        """Deduplicates and sorts deps alphabetically across all addons."""
        self._write_reqs(tmp_path)
        addons = [
            _make_addon("a", ["zebra", "requests", "PIL"]),
            _make_addon("b", ["requests", "lxml"]),  # requests appears in both addons
        ]
        self._patch_addons(monkeypatch, addons)

        _, new_lines, _ = get_requirements_diff(tmp_path)

        deps = new_lines[1:]  # skip the header comment
        assert deps == sorted(deps)  # alphabetical order
        assert deps.count("requests") == 1  # no duplicates
        assert "Pillow" in deps  # PIL was mapped to its pip name

    def test_ignored_deps(self, tmp_path, monkeypatch):
        """Ignores everything outside the 'python' key of external_dependencies."""
        cases = {
            # addon has no external_dependencies at all
            "no python key": (_make_addon_full_deps("a", {}), [HEADER], []),
            # addon declares external_dependencies but python list is empty
            "empty python list": (_make_addon_full_deps("a", {"python": []}), [HEADER], []),
            # system-level deps under 'bin' must not pollute the python output
            "bin key ignored": (
                _make_addon_full_deps("a", {"python": ["requests"], "bin": ["wkhtmltopdf"]}),
                [HEADER, "requests"],
                ["wkhtmltopdf"],
            ),
        }
        for description, (addon, expected_in, expected_not_in) in cases.items():
            self._write_reqs(tmp_path)
            self._patch_addons(monkeypatch, [addon])

            _, new_lines, _ = get_requirements_diff(tmp_path)

            for item in expected_in:
                assert item in new_lines, description
            for item in expected_not_in:
                assert item not in new_lines, description

    def test_diff_output(self, tmp_path, monkeypatch):
        """Returns a standard ndiff: '+' for additions, '-' for removals, no prefix when in sync."""
        # new dep in manifests not yet in the file → appears as an addition
        self._write_reqs(tmp_path, "")
        self._patch_addons(monkeypatch, [_make_addon("a", ["requests"])])
        _, _, diff = get_requirements_diff(tmp_path)
        assert any(line.startswith("+") and "requests" in line for line in diff), "added dep marked +"

        # dep in the file no longer declared by any manifest → appears as removal
        self._write_reqs(tmp_path, "old-dep\n")
        self._patch_addons(monkeypatch, [_make_addon("a", ["requests"])])
        _, _, diff = get_requirements_diff(tmp_path)
        assert any(line.startswith("-") and "old-dep" in line for line in diff), "removed dep marked -"

        # file already matches the manifests → no +/- markers at all
        self._write_reqs(tmp_path, "requests\n")
        self._patch_addons(monkeypatch, [_make_addon("a", ["requests"])])
        _, _, diff = get_requirements_diff(tmp_path)
        assert not any(line.startswith(("+", "-")) for line in diff), "no marks when in sync"

    @pytest.mark.parametrize(
        "description, manifest_deps, expected_output",
        [
            # Add test cases below. Both manifest_deps and expected_output are plain
            # strings (same format as a requirements file). Comment lines are ignored.
            (
                "new dep added to empty file",
                "requests",
                """\
                # generated from manifests external_dependencies
                requests""",
            ),
            (
                "same content",
                """\
                google_auth
                odoo_upgrade@git+https://github.com/odoo/upgrade-util@master
                packaging
                python-barcode
                sentry_sdk>=2.0.0,<=2.22.0""",
                """\
                # generated from manifests external_dependencies
                google_auth
                odoo_upgrade@git+https://github.com/odoo/upgrade-util@master
                packaging
                python-barcode
                sentry_sdk>=2.0.0,<=2.22.0""",
            ),
            (
                "git requirement passes through unchanged",
                "odoo_upgrade@git+https://github.com/odoo/upgrade-util@master",
                """\
                # generated from manifests external_dependencies
                odoo_upgrade@git+https://github.com/odoo/upgrade-util@master""",
            ),
            (
                "name mapping PIL to Pillow with version",
                "PIL>=9.0",
                """\
                # generated from manifests external_dependencies
                Pillow>=9.0""",
            ),
            (
                "equality pin kept as-is",
                "requests==2.28.0",
                """\
                # generated from manifests external_dependencies
                requests==2.28.0""",
            ),
            (
                "alphabetical sort",
                """\
                zebra
                alpha
                mango""",
                """\
                # generated from manifests external_dependencies
                alpha
                mango
                zebra""",
            ),
        ],
    )
    def test_string_cases(
        self,
        tmp_path: Path,
        monkeypatch,
        description: str,
        manifest_deps: str,
        expected_output: str,
    ):
        """Simple string-based parametrized cases: put manifest deps and expected output as plain strings."""
        deps = [
            line.strip() for line in manifest_deps.splitlines() if line.strip() and not line.strip().startswith("#")
        ]
        self._write_reqs(tmp_path)
        self._patch_addons(monkeypatch, [_make_addon("addon", deps)])

        _, new_lines, _ = get_requirements_diff(tmp_path)

        assert "\n".join(new_lines) == textwrap.dedent(expected_output).strip(), description
