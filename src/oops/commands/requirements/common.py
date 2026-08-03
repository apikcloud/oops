# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: common.py — src/oops/commands/requirements/common.py


from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from oops.core.checks import Check, CheckContext, CheckOutcome
from oops.core.models import Result
from oops.io.requirements import (
    _gather_repository_requirements,
    generate_requirements,
    get_requirements_with_conflicting_exact_pins,
    get_requirements_with_contradictory_range,
    get_requirements_with_unsupported_operator,
)


@dataclass
class RequirementsCheckContext(CheckContext):
    requirement_file: Path
    path: Path

    @cached_property
    def gathered_requirements(self) -> tuple:
        """Parse repository requirements once and cache the result."""
        return _gather_repository_requirements(self.path, allow_not_equal_operator=True)


class RequirementsCheck(Check[RequirementsCheckContext]):
    name = "external_dep"
    label = "External dependencies"

    def _run(self) -> Result[CheckOutcome]:
        has_changes, _, diff = generate_requirements(self.ctx.path)

        if has_changes:
            self.add(status="failed", items=diff)
            self.result.add_error("Requirements differ. See output above.")
        else:
            self.add(status="passed")

        return self.result


class RequirementsWithUnsupportedOperator(Check[RequirementsCheckContext]):
    name = "requirements_with_unsupported_operator"
    label = "Unsupported operator"

    def _run(self) -> Result[CheckOutcome]:
        all_constraints, constraint_to_addons, _, _ = self.ctx.gathered_requirements
        problematic_requirements = get_requirements_with_unsupported_operator(all_constraints, constraint_to_addons)

        if problematic_requirements:
            self.add(status="failed", items=problematic_requirements)
            self.result.add_error("Requirements with unsupported operator detected. See output above.")
        else:
            self.add(status="passed")

        return self.result


class ConflictingExactPinsRequirements(Check[RequirementsCheckContext]):
    name = "conflicting_exact_pins"
    label = 'Conflicting "==" pins'

    def _run(self) -> Result[CheckOutcome]:
        all_constraints, constraint_to_addons, _, _ = self.ctx.gathered_requirements
        problematic_requirements = get_requirements_with_conflicting_exact_pins(all_constraints, constraint_to_addons)

        if problematic_requirements:
            self.add(status="failed", items=problematic_requirements)
            self.result.add_error("Requirements with conflicting exact pins detected. See output above.")
        else:
            self.add(status="passed")

        return self.result


class InvalidRangeRequirements(Check[RequirementsCheckContext]):
    name = "invalid_range_requirements"
    label = "Contradictory ranges"

    def _run(self) -> Result[CheckOutcome]:
        all_constraints, constraint_to_addons, _, _ = self.ctx.gathered_requirements
        problematic_requirements = get_requirements_with_contradictory_range(all_constraints, constraint_to_addons)

        if problematic_requirements:
            self.add(status="failed", items=problematic_requirements)
            self.result.add_error("Requirements with contradictory ranges detected. See output above.")
        else:
            self.add(status="passed")

        return self.result


class ImportsCheck(Check[RequirementsCheckContext]):
    name = "imports"
    label = "From imports"

    def _run(self) -> Result[CheckOutcome]:
        return self.result
