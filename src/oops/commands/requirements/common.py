# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: common.py — src/oops/commands/requirements/common.py


from dataclasses import dataclass
from pathlib import Path

from oops.core.checks import Check, CheckContext, CheckOutcome
from oops.core.models import Result
from oops.io.file import get_requirements_diff


@dataclass
class RequirementsCheckContext(CheckContext):
    requirement_file: Path
    path: Path


class RequirementsCheck(Check[RequirementsCheckContext]):
    name = "external_dep"
    label = "External dependencies"

    def _run(self) -> Result[CheckOutcome]:

        has_changes, _, diff = get_requirements_diff(self.ctx.path)

        if not has_changes:
            self.add(status="passed")
            return self.result

        self.add(status="failed", items=diff)
        self.result.add_error("Requirements differ. See output above.")

        return self.result


class ImportsCheck(Check[RequirementsCheckContext]):
    name = "imports"
    label = "From imports"

    def _run(self) -> Result[CheckOutcome]:

        return self.result
