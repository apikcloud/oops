# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/depends/presenters/show.py

from __future__ import annotations

from oops.core.models import Result
from oops.output.base import SimplePresenter


class ShowPresenter(SimplePresenter[dict]):
    def to_machine(self, result: Result[dict]) -> dict:

        data = result.unwrap

        return {
            "warnings": result.warnings,
            "stats": data.get("metrics"),
            "addons": data.get("addons"),
        }
