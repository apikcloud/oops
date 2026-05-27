# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: materialize.py — src/oops/commands/addons/presenters/materialize.py

from __future__ import annotations

from oops.core.compat import TYPE_CHECKING
from oops.core.models import Result
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, Output, SimpleSummaryLayout, TableBlock

if TYPE_CHECKING:
    from oops.output.base import RenderTarget


def prepare(result: "Result[dict]", outer: "Result[None]", target: RenderTarget) -> Output:
    data = result.data
    assert data

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
    all_ok = counts["failed"] == 0 and not outer.errors
    if dry_run:
        conclusion_msg = "Dry run — no changes committed"
    elif all_ok:
        conclusion_msg = f"Materialized {counts['materialized']} addon(s)"
    else:
        conclusion_msg = f"{counts['failed']} addon(s) failed"

    return Output(
        SimpleSummaryLayout(
            title=data.get("cmd", "Materialize addons"),
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(all_ok, conclusion_msg),
            warnings=outer.warnings + result.warnings,
            errors=outer.errors + result.errors,
        )
    )
