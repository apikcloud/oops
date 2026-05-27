# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — src/oops/commands/addons/presenters/download.py

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
    counts = {"downloaded": 0, "skipped": 0}
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
            ["Downloaded", str(counts["downloaded"])],
            ["Skipped", str(counts["skipped"])],
        ],
    )

    all_ok = counts["downloaded"] > 0 or counts["skipped"] > 0
    conclusion_msg = f"Downloaded {counts['downloaded']} addon(s)" if counts["downloaded"] else "Nothing downloaded"

    return Output(
        SimpleSummaryLayout(
            title=data.get("cmd", "Download addons"),
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(all_ok, conclusion_msg),
            warnings=outer.warnings,
        )
    )
