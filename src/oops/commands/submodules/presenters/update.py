# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — src/oops/commands/submodules/presenters/update.py

from __future__ import annotations

from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, SimpleSummaryLayout, TableBlock
from oops.utils.render import colorize

COLOR_STATUS = {
    "failed": "red",
    "updated": "green",
    "planned": "green",
    "no change": "dim",
    "skipped": "dim gray50",
}


class UpdatePresenter(SimplePresenter[dict]):
    def to_human(self, result: "Result[dict]") -> SimpleSummaryLayout:
        data = result.unwrap

        def _prepare_row(row: dict) -> list:
            return [
                row["submodule"],
                row["branch"],
                colorize(row["action"], COLOR_STATUS.get(row["action"], "dim")),
            ]

        rows = data.get("rows", [])

        from collections import Counter

        counts = Counter(row["action"] for row in rows)

        table = TableBlock(
            title="",
            columns=[
                ("Submodule", "brand.primary", "left"),
                ("Branch", "dim", "left"),
                ("Status", "green", "left"),
            ],
            rows=[_prepare_row(row) for row in rows],
        )

        panel = MetricsPanelBlock(
            "Summary",
            [
                ["Total", str(len(rows))],
                ["Updated", str(counts["updated"])],
                ["Skipped", str(counts["skipped"])],
                ["Planned", str(counts["planned"])],
                ["Failed", str(counts["failed"])],
            ],
        )

        dry_run = data.get("dry_run", False)
        conclusion_msg = "Dry run — no changes committed" if dry_run else "Submodules up to date"

        return SimpleSummaryLayout(
            title=data.get("cmd", "Update submodules"),
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(True, conclusion_msg),
            warnings=result.warnings,
            errors=result.errors,
        )
