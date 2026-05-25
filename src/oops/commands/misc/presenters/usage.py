# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: usage.py — src/oops/commands/misc/presenters/usage.py

from __future__ import annotations

from oops.core.models import Result
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, Output, SimpleSummaryLayout, TableBlock


def prepare_full(result: "Result[dict]", outer: "Result[None]") -> "Output[dict]":
    assert result.data
    return Output(
        {
            "warnings": outer.warnings,
            "rows": result.data["rows"],
            "from": result.data["from"],
        }
    )


def prepare_summary(result: "Result[dict]", outer: "Result[None]") -> "Output[SimpleSummaryLayout]":
    data = result.data
    assert data

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

    return Output(
        SimpleSummaryLayout(
            title="oops usage",
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(True, "Usage report"),
            warnings=outer.warnings,
        )
    )


def prepare(result: "Result[dict]", outer: "Result[None]", target: str) -> Output:
    if target == "machine":
        return prepare_full(result, outer)
    return prepare_summary(result, outer)
