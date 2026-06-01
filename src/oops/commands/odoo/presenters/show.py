# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — src/oops/commands/odoo/presenters/update.py

from __future__ import annotations

from oops.core.compat import Dict
from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import (
    ConclusionBlock,
    MetricsPanelBlock,
    SimpleSummaryLayout,
    TableBlock,
)


class ShowPresenter(SimplePresenter[Dict]):
    def to_machine(self, result: "Result[Dict]") -> dict:

        data = result.unwrap

        return {
            "warnings": result.warnings,
            "sources": data["rows"],
            "metrics": data["metrics"],
        }

    def to_human(self, result: "Result[Dict]") -> "SimpleSummaryLayout":
        data = result.unwrap

        rows = data.pop("rows")
        metrics = data.pop("metrics")

        panel = MetricsPanelBlock("Summary", values=[[k.capitalize(), v] for k, v in metrics.items()])

        table = TableBlock(
            title="",
            columns=[
                ("Version", "brand.primary", "left"),
                ("Community", "dim", "left"),
                ("Enterprise", "dim", "left"),
                ("Themes", "dim", "left"),
            ],
            rows=[[row["version"], row["community"], row["enterprise"], row["themes"]] for row in rows],
        )

        if not rows:
            message = "No version directories found"
        elif result.ok:
            message = "All done"
        else:
            message = "Command failed"

        return SimpleSummaryLayout(
            title="Odoo Sources",
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(result.ok, message),
            warnings=result.warnings,
            errors=result.errors,
        )
