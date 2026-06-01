# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: materialize.py — src/oops/commands/addons/presenters/materialize.py

from __future__ import annotations

from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, SimpleSummaryLayout, TableBlock


class MaterializePresenter(SimplePresenter[dict]):
    def to_human(self, result: Result[dict]) -> SimpleSummaryLayout:

        data = result.unwrap

        rows = data.get("rows", [])
        counts = {"materialized": 0, "failed": 0, "planned": 0}
        for row in rows:
            action = row.get("action", "")
            if action in counts:
                counts[action] += 1

        table = TableBlock(
            title="",
            columns=[
                ("Addon", "brand.primary", "left"),
                ("Status", "green", "left"),
            ],
            rows=[[row["addon"], row["action"]] for row in rows],
        )

        panel = MetricsPanelBlock(
            "Summary",
            [
                ["Materialized", str(counts["materialized"])],
                ["Planned", str(counts["planned"])],
                ["Failed", str(counts["failed"])],
            ],
        )

        dry_run = data.get("dry_run", False)
        all_ok = result.ok and counts["failed"] == 0
        if dry_run:
            conclusion_msg = "Dry run — no changes committed"
        elif all_ok:
            conclusion_msg = f"Materialized {counts['materialized']} addon(s)"
        else:
            conclusion_msg = f"{counts['failed']} addon(s) failed"

        return SimpleSummaryLayout(
            title=data.get("cmd", "Materialize addons"),
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(all_ok, conclusion_msg),
            warnings=result.warnings,
            errors=result.errors,
        )
