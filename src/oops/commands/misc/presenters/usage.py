# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: usage.py — src/oops/commands/misc/presenters/usage.py

from __future__ import annotations

from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, SimpleSummaryLayout, TableBlock


class UsagePresenter(SimplePresenter[dict]):
    def to_machine(self, result: "Result[dict]") -> dict:

        data = result.unwrap

        return {
            "warnings": result.warnings,
            "rows": data["rows"],
            "from": data["from"],
        }

    def to_human(self, result: "Result[dict]") -> SimpleSummaryLayout:
        data = result.unwrap

        rows = data["rows"]
        total = sum(r["count"] for r in rows)

        table = TableBlock(
            title="",
            columns=[
                ("Scope", "dim", "left"),
                ("Command", "brand.primary", "left"),
                ("Count", "green", "right"),
            ],
            rows=[[r["scope"], r["command"], str(r["count"])] for r in rows],
        )

        panel = MetricsPanelBlock(
            "Summary",
            [
                ["From", data["from"] or "—"],
                ["Total", str(total)],
                ["Commands", str(len(rows))],
            ],
        )

        return SimpleSummaryLayout(
            title="oops usage",
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(True, "Usage report"),
            warnings=result.warnings,
            errors=result.errors,
        )
