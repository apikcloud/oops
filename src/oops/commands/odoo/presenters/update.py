# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — src/oops/commands/odoo/presenters/update.py

from __future__ import annotations

from oops.core.compat import Dict
from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, SimpleSummaryLayout, TableBlock


class UpdatePresenter(SimplePresenter[Dict]):
    def to_machine(self, result: "Result[Dict]") -> dict:

        data = result.unwrap

        return {
            "warnings": result.warnings,
            "repos": data["rows"],
        }

    def to_human(self, result: "Result[Dict]") -> "SimpleSummaryLayout":
        data = result.unwrap

        rows = data.get("rows", [])
        counts = {"updated": 0, "skipped": 0, "failed": 0}
        for row in rows:
            action = row.get("action", "")
            if action in counts:
                counts[action] += 1

        table = TableBlock(
            title="",
            columns=[
                ("Repo", "brand.primary", "left"),
                ("Action", "green", "left"),
                ("Detail", "dim", "left"),
            ],
            rows=[[row["repo"], row["action"], row["detail"]] for row in rows],
        )

        panel = MetricsPanelBlock(
            "Summary",
            [
                ["Updated", str(counts["updated"])],
                ["Skipped", str(counts["skipped"])],
                ["Failed", str(counts["failed"])],
            ],
        )

        all_ok = result.ok and counts["failed"] == 0
        return SimpleSummaryLayout(
            title=data.get("cmd", "Update Odoo sources"),
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(all_ok, "Sources up to date" if all_ok else "Some repos failed"),
            warnings=result.warnings,
        )
