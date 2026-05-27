# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — src/oops/commands/submodules/presenters/update.py

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
    counts = {"updated": 0, "skipped": 0, "planned": 0}
    for row in rows:
        action = row.get("action", "")
        if action in counts:
            counts[action] += 1

    table = TableBlock(
        title="",
        columns=[
            ("Submodule", "brand.primary", "left"),
            ("Branch", "dim", "left"),
            ("Status", "green", "left"),
        ],
        rows=[[row["submodule"], row["branch"], row["action"]] for row in rows],
    )

    panel = MetricsPanelBlock(
        "Summary",
        [
            ["Updated", str(counts["updated"])],
            ["Skipped", str(counts["skipped"])],
            ["Planned", str(counts["planned"])],
        ],
    )

    dry_run = data.get("dry_run", False)
    conclusion_msg = "Dry run — no changes committed" if dry_run else "Submodules up to date"

    return Output(
        SimpleSummaryLayout(
            title=data.get("cmd", "Update submodules"),
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(True, conclusion_msg),
            warnings=outer.warnings,
        )
    )
