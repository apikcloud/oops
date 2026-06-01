# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: build_global.py — src/oops/commands/misc/presenters/build_global.py


from __future__ import annotations

from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, SimpleSummaryLayout, TableBlock


class BuildGlobalPresenter(SimplePresenter[dict]):
    def to_machine(self, result: "Result[dict]") -> dict:

        return {
            "warnings": result.warnings,
            "addons": result.data,
        }

    def to_human(self, result: "Result[dict]") -> SimpleSummaryLayout:

        data = result.unwrap

        # Summary table
        table = TableBlock(
            title="",
            columns=[
                ("Name", "brand.primary", "left"),
                ("Path", "dim", "left"),
                ("Modules", "green", "left"),
            ],
            rows=[
                [
                    row["name"],
                    str(row["path"]),
                    str(row["modules"]),
                ]
                for row in data["stats"]
            ],
        )

        # Stats Panel
        panel = MetricsPanelBlock(
            "Summary",
            [
                ["Modules", str(data["kb"]["modules"])],
                ["Symbols", str(data["kb"]["symbols"])],
                ["Fields", str(data["kb"]["fields"])],
                ["Methods", str(data["kb"]["methods"])],
                ["Views", str(data["kb"]["views"])],
                ["Actions", str(data["kb"]["actions"])],
                ["Menus", str(data["kb"]["menus"])],
            ],
        )

        return SimpleSummaryLayout(
            title=data["cmd"],
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(True, "All done"),
            warnings=result.warnings,
            errors=result.errors,
        )
