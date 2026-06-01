# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — src/oops/commands/odoo/presenters/download.py

from __future__ import annotations

from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, SimpleSummaryLayout, TableBlock


class DownloadPresenter(SimplePresenter[dict]):
    def to_machine(self, result: "Result[dict]") -> dict:
        data = result.unwrap
        return {"repos": data.get("rows", []), "warnings": result.warnings}

    def to_human(self, result: "Result[dict]") -> SimpleSummaryLayout:
        data = result.unwrap

        rows = data.get("rows", [])
        counts = {"cloned": 0, "updated": 0, "skipped": 0, "failed": 0}
        for row in rows:
            action = row.get("action", "")
            if action in counts:
                counts[action] += 1

        table = TableBlock(
            title="",
            columns=[
                ("Repo", "brand.primary", "left"),
                ("Action", "green", "left"),
                ("Status", "dim", "left"),
            ],
            rows=[[row["repo"], row["action"], row["status"]] for row in rows],
        )

        panel = MetricsPanelBlock(
            "Summary",
            [
                ["Cloned", str(counts["cloned"])],
                ["Updated", str(counts["updated"])],
                ["Skipped", str(counts["skipped"])],
                ["Failed", str(counts["failed"])],
            ],
        )

        all_ok = result.ok and counts["failed"] == 0
        return SimpleSummaryLayout(
            title=data.get("cmd", "Download Odoo sources"),
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(all_ok, "Sources ready" if all_ok else "Some repos failed"),
            warnings=result.warnings,
            errors=result.errors,
        )
