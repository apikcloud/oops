# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/project/presenters/show.py

from __future__ import annotations

from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsLayout, MetricsPanelBlock


class ShowPresenter(SimplePresenter[dict]):
    def to_machine(self, result: Result[dict]) -> dict:
        data = result.unwrap

        return {
            "warnings": result.warnings,
            "project": data["project"],
            "metrics": data["metrics"],
        }

    def to_human(self, result: Result[dict]) -> MetricsLayout:

        data = result.unwrap

        metrics = [MetricsPanelBlock(k.capitalize(), v) for k, v in data["metrics"].items()]

        return MetricsLayout(
            title=f"Project status - {data['project']}",
            panels=metrics,
            conclusion=ConclusionBlock(True, "Status report"),
            warnings=result.warnings,
            errors=result.errors,
        )
