# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: build_global.py — src/oops/commands/misc/presenters/build_global.py


from __future__ import annotations

from oops.core.compat import TYPE_CHECKING
from oops.core.models import Result
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, Output, SimpleSummaryLayout, TableBlock

if TYPE_CHECKING:
    from oops.output.base import RenderTarget


def prepare_full(result: "Result[dict]", outer: "Result[None]") -> "Output[dict]":
    return Output(
        {
            "warnings": outer.warnings,
            "addons": result.data,
        }
    )


def prepare_summary(result: "Result[dict]", outer: "Result[None]") -> "Output[SimpleSummaryLayout]":

    data = result.data
    assert data

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

    return Output(
        SimpleSummaryLayout(
            title=data["cmd"],
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(True, "All done"),
            warnings=outer.warnings,
        )
    )


def prepare(result: "Result[dict]", outer: "Result[None]", target: RenderTarget) -> Output:
    if target.audience == "machine":
        return prepare_full(result, outer)
    return prepare_summary(result, outer)
