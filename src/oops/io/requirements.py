# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: requirements.py — oops/io/requirements.py

"""
Helpers for reading, generating, and validating the project Python requirements file.

Sections:
    - Parsing: read the current requirements file from disk
    - Resolution: collect deps from addon manifests and resolve version constraints
    - Generation: produce the up-to-date requirements content and diff it against the file
    - Validation: detect conflicting or unsupported constraints across addons
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.io.file import find_addons, read_and_parse
from packaging import version


# --------------------------------------------------
# Parser
# --------------------------------------------------
def parse_requirements(project_path: Path) -> list:
    """Read and return the sorted list of entries from the project requirements file.

    Args:
        project_path: Project root directory containing the requirements file.

    Returns:
        Sorted list of requirement strings, or an empty list if the file does not exist.
    """
    requirements_file = project_path / config.project.file_requirements
    if not requirements_file.exists():
        return []
    return read_and_parse(requirements_file, unique=False)


# --------------------------------------------------
# All requirements generation
# --------------------------------------------------
def generate_requirements(repository_path: Path, gathered: tuple | None = None) -> tuple[bool, list[str], list[str]]:
    """Generate requirements.txt content from addon manifests and diff it against the current file.

    Args:
        repository_path: Root of the repository to scan for addons.
        gathered: Optional pre-gathered tuple from ``gather_repository_requirements`` (with
            ``allow_not_equal_operator=True``). When provided, the filesystem scan is skipped.

    Returns:
        A tuple (has_changes, generated_lines, diff_lines):
        - has_changes: True if generated content differs from the existing file.
        - generated_lines: Sorted list of dependency lines (with header comment).
        - diff_lines: Raw output from difflib.ndiff.
    """
    if gathered is None:
        all_constraint_keys, _, package_version_map, pinned_package_names = gather_repository_requirements(
            repository_path, allow_not_equal_operator=True
        )
    else:
        all_constraint_keys, _, _, _ = gathered
        package_version_map = _categorize_versions_by_operator(sorted(all_constraint_keys))
        pinned_package_names = {
            re.split("[<=>]", c)[0].strip() for c in all_constraint_keys if re.match(r"[^<>=!]*==", c)
        }

    resolved_dependencies = []

    # Merge range constraints per package into the tightest floor and ceiling
    for package_name, operators in package_version_map.items():
        if package_name in pinned_package_names:
            continue

        lower_bound = _find_best_version_boundary([">", ">="], ">", operators, is_lower_bound=True)
        upper_bound = _find_best_version_boundary(["<", "<="], "<", operators, is_lower_bound=False)

        if lower_bound and upper_bound:
            resolved_dependencies.append(f"{package_name}{lower_bound},{upper_bound}")
        elif lower_bound:
            resolved_dependencies.append(f"{package_name}{lower_bound}")
        elif upper_bound:
            resolved_dependencies.append(f"{package_name}{upper_bound}")

    # Add unhandled constraints as-is (unconstrained packages, exact == pins, and unsupported != specs)
    known_packages = set(package_version_map.keys())
    for constraint in sorted(all_constraint_keys):
        package_name = re.split("[<=>]", constraint)[0].strip()
        is_exact_pin = bool(re.match(r"[^<>=!]*==", constraint))
        is_unsupported_op = "!=" in constraint

        if package_name not in known_packages or is_exact_pin or is_unsupported_op:
            resolved_dependencies.append(constraint)

    resolved_dependencies = sorted(resolved_dependencies)

    current_requirements = parse_requirements(repository_path)
    diff_lines = list(difflib.ndiff(current_requirements, resolved_dependencies))
    has_changes = any(line.startswith(("-", "+")) for line in diff_lines)

    header_comment = "# generated from manifests external_dependencies"
    generated_lines = [header_comment] + resolved_dependencies

    return has_changes, generated_lines, diff_lines


# --------------------------------------------------
# Problematic requirements management
# --------------------------------------------------
def get_requirements_with_conflicting_exact_pins(
    all_constraints: set[str],
    constraint_to_addons: dict[str, set[str]],
) -> list[str]:
    """Get requirements with conflicting exact version pins (==).

    When multiple different exact pins are specified for the same package (e.g.,
    pandas==1.2.0 and pandas==1.3.0 across different addons), they override each
    other and lead to dependency resolution issues.

    Args:
        all_constraints: Set of individual constraint strings collected from all addon manifests.
        constraint_to_addons: Mapping from each constraint string to the set of addon technical names
            that declare it.

    Returns:
        A list formatted like ["ADDON: package==version"] detailing the detected conflicts.
    """
    detected_issues = []
    valid_range_constraints = _exclude_unsupported(all_constraints)

    exact_pins_by_package: dict[str, list[str]] = {}
    for constraint in sorted(valid_range_constraints):
        if re.match(r"[^<>=!]*==", constraint):
            package_name = re.split("[<=>]", constraint)[0].strip()
            exact_pins_by_package.setdefault(package_name, []).append(constraint)

    for _, pins in sorted(exact_pins_by_package.items()):
        if len(pins) > 1:
            for pin in sorted(pins):
                for addon in sorted(constraint_to_addons.get(pin, set())):
                    detected_issues.append(f"{addon}: {pin}")

    return detected_issues


def get_requirements_with_contradictory_range(
    all_constraints: set[str],
    constraint_to_addons: dict[str, set[str]],
) -> list[str]:
    """Get the requirements with contradictory ranges.
    A contradictory range means the tool cannot choose which requirement apply.
    For example:
        pandas>1.0.0 and pandas<1.0.0 is a contradictory range as it can't be both below and over 1.0.0.

    Args:
        all_constraints: Set of individual constraint strings collected from all addon manifests.
        constraint_to_addons: Mapping from each constraint string to the set of addon technical names
            that declare it.

    Returns:
        A list of packages with contradictory ranges.
    """
    detected_issues = []
    valid_range_constraints = _exclude_unsupported(all_constraints)

    unpinned_constraints = [c for c in valid_range_constraints if not re.match(r"[^<>=!]*==", c)]
    grouped_unpinned_versions = _categorize_versions_by_operator(sorted(unpinned_constraints))

    for package_name, operators in sorted(grouped_unpinned_versions.items()):
        lower_bound_str = _find_best_version_boundary([">", ">="], ">", operators, is_lower_bound=True)
        upper_bound_str = _find_best_version_boundary(["<", "<="], "<", operators, is_lower_bound=False)

        if not lower_bound_str or not upper_bound_str:
            continue

        lower_version_raw = re.sub(r"^[><=]+", "", lower_bound_str)
        upper_version_raw = re.sub(r"^[><=]+", "", upper_bound_str)

        parsed_lower = version.parse(lower_version_raw)
        parsed_upper = version.parse(upper_version_raw)

        if parsed_lower >= parsed_upper:
            lower_constraint = f"{package_name}{lower_bound_str}"
            upper_constraint = f"{package_name}{upper_bound_str}"
            for addon in sorted(constraint_to_addons.get(lower_constraint, set())):
                detected_issues.append(f"{addon}: {lower_constraint}")
            for addon in sorted(constraint_to_addons.get(upper_constraint, set())):
                detected_issues.append(f"{addon}: {upper_constraint}")

    return detected_issues


def get_requirements_with_unsupported_operator(
    all_constraints: set[str],
    constraint_to_addons: dict[str, set[str]],
) -> list[str]:
    """Get the requirements with unsupported operator, at the moment only the "!=" operator is forbidden.

    Args:
        all_constraints: Set of individual constraint strings collected from all addon manifests.
        constraint_to_addons: Mapping from each constraint string to the set of addon technical names
            that declare it.

    Returns:
        A list formatted like ["MODULE: pandas!=1.2"] to display the origin of the wrong operator.
    """
    detected_issues = []
    for constraint in sorted(all_constraints):
        if "!=" in constraint:
            for addon in sorted(constraint_to_addons.get(constraint, set())):
                detected_issues.append(f"{addon}: {constraint}")

    return detected_issues


# --------------------------------------------------
# Private functions
# --------------------------------------------------
def _exclude_unsupported(constraints: set[str]) -> list[str]:
    """Return constraints without unsupported (``!=``) operators."""
    return [c for c in constraints if "!=" not in c]


def _categorize_versions_by_operator(raw_dependency_specs: list[str]) -> dict[str, dict[str, list[str]]]:
    """Group versioned dependencies by package name and comparison operator (>=, >, <=, <).

    Returns a dict mapping package_name → {">=": [...], ">": [...], "<=": [...], "<": [...]}.
    Exact matches (==) or unconstrained packages are intentionally excluded here.
    """
    # Order operators to ensure composite operators (<=, >=) are checked before single character ones (<, >)
    comparison_operators = ["<=", ">=", "<", ">"]
    packages_by_operator: dict[str, dict[str, list[str]]] = {}

    for spec in raw_dependency_specs:
        package_name = re.split("[<=>]", spec)[0]
        version_segments = spec.split(package_name)[1].split(",")
        expanded_constraints = [f"{package_name}{v}" for v in version_segments if v.strip() != ""]

        for constraint in expanded_constraints:
            for operator in comparison_operators:
                parts = constraint.split(operator)
                if len(parts) > 1:
                    if package_name not in packages_by_operator:
                        packages_by_operator[package_name] = {">": [], "<": [], "<=": [], ">=": []}
                    packages_by_operator[package_name][operator].append(parts[-1])
                    break

    return packages_by_operator


def _fetch_addon_dependencies(
    repository_path: Path,
    package_mapping: dict[str, str],
    allow_not_equal_operator: bool = False,
) -> dict[str, list[str]]:
    """Scan all addons under repository_path and return python dependencies per addon with mapped names.

    Args:
        repository_path: Root directory to scan for addons.
        package_mapping: Translation map from manifest dep names to PyPI package names.
        allow_not_equal_operator: If False, dependencies with ``!=`` are ignored.
    """
    addon_dependencies = {}

    for addon in find_addons(repository_path, shallow=True):
        addon_dependencies[addon.technical_name] = []
        for dependency in addon.external_dependencies.get("python", []):
            if "!=" in dependency and not allow_not_equal_operator:
                continue

            matching_operator = re.search("[<=>!]" if allow_not_equal_operator else "[<=>]", dependency)
            if matching_operator:
                raw_package_name = dependency[: matching_operator.start()].strip()
                version_constraint = dependency[matching_operator.start() :].strip()
            else:
                raw_package_name = dependency.strip()
                version_constraint = ""

            resolved_package_name = package_mapping.get(raw_package_name, raw_package_name)
            addon_dependencies[addon.technical_name].append(f"{resolved_package_name}{version_constraint}")

    return addon_dependencies


def _find_best_version_boundary(
    operators: list[str],
    preferred_strict_operator: str,
    operator_versions: dict[str, list[str]],
    is_lower_bound: bool = True,
) -> str:
    """Pick the tightest version boundary from a set of operator/version pairs.

    For a lower bound / floor (is_lower_bound=True) returns the highest version found.
    For an upper bound / ceiling (is_lower_bound=False) returns the lowest version found.
    When two operators target the same version, the strict one (> or <) takes precedence over >= or <=.
    """
    selected_operator = ""
    selected_version = None

    for operator in operators:
        versions_for_operator = operator_versions.get(operator, [])
        if not versions_for_operator:
            continue

        try:
            candidate_version = (
                max(versions_for_operator, key=version.parse)
                if is_lower_bound
                else min(versions_for_operator, key=version.parse)
            )

            if selected_version is None:
                selected_version = candidate_version
                selected_operator = operator
            elif is_lower_bound and version.parse(candidate_version) > version.parse(selected_version):
                selected_version = candidate_version
                selected_operator = operator
            elif not is_lower_bound and version.parse(candidate_version) < version.parse(selected_version):
                selected_version = candidate_version
                selected_operator = operator
            elif (
                version.parse(candidate_version) == version.parse(selected_version)
                and operator == preferred_strict_operator
            ):
                selected_operator = preferred_strict_operator

        except version.InvalidVersion as error:
            raise OopsError(f"Invalid version string in external dependency: {error}") from error

    return f"{selected_operator}{selected_version}" if selected_version else ""


def gather_repository_requirements(
    repository_path: Path,
    allow_not_equal_operator: bool = False,
) -> tuple[set[str], dict[str, set[str]], dict[str, dict[str, list[str]]], set[str]]:
    """Collect, expand, and structure all python dependencies declared in addon manifests.

    Args:
        repository_path: Root of the repository to scan for addons.
        allow_not_equal_operator: When True, dependencies using ``!=`` are included.

    Returns:
        A tuple (all_constraint_keys, constraint_to_addons, package_version_map, pinned_package_names):
        - all_constraint_keys: Set of individual constraint strings.
        - constraint_to_addons: Individual constraint string → set of addon technical names.
        - package_version_map: Grouped range versions per package and operator.
        - pinned_package_names: Set of package names pinned with an exact version (==).
    """
    addon_raw_dependencies = _fetch_addon_dependencies(
        repository_path,
        config.requirements.python_requirements_mapping,
        allow_not_equal_operator=allow_not_equal_operator,
    )

    constraint_to_addons: dict[str, set[str]] = {}
    for addon_name, dependencies in addon_raw_dependencies.items():
        if not addon_name:
            continue
        for dependency in dependencies:
            package_name = re.split("[<=>!]", dependency)[0].strip()
            version_part = dependency[len(package_name) :]

            for single_constraint in version_part.split(","):
                single_constraint = single_constraint.strip()
                lookup_key = f"{package_name}{single_constraint}" if single_constraint else package_name
                constraint_to_addons.setdefault(lookup_key, set()).add(addon_name)

    all_constraint_keys = set(constraint_to_addons.keys())
    package_version_map = _categorize_versions_by_operator(sorted(all_constraint_keys))

    pinned_package_names = {
        re.split("[<=>]", constraint)[0].strip()
        for constraint in all_constraint_keys
        if re.match(r"[^<>=!]*==", constraint)
    }

    return all_constraint_keys, constraint_to_addons, package_version_map, pinned_package_names
