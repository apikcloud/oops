# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — src/oops/commands/odoo/presenters/download.py

from __future__ import annotations

from oops.core.compat import TYPE_CHECKING
from oops.core.metadata import Metadata
from oops.core.models import Result
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, Output, SimpleSummaryLayout, TableBlock

if TYPE_CHECKING:
    from oops.output.base import RenderTarget


def prepare_full(
    result: "Result[dict]",
    outer: "Result[None]",
    metadata: Metadata,
) -> "Output[dict]":
    return Output(
        {
            "metadata": metadata.to_dict(),
            "warnings": outer.warnings,
            "repos": result.data["rows"] if result.data else [],
        }
    )


def prepare_summary(
    result: "Result[dict]",
    outer: "Result[None]",
    metadata: Metadata,
) -> "Output[SimpleSummaryLayout]":
    data = result.data
    assert data

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

    all_ok = counts["failed"] == 0
    out = Output(
        SimpleSummaryLayout(
            title=data.get("cmd", "Download Odoo sources"),
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(all_ok, "Sources ready" if all_ok else "Some repos failed"),
            warnings=outer.warnings,
        )
    )
    out.metadata = metadata
    return out


def prepare(result: "Result[dict]", outer: "Result[None]", target: RenderTarget, metadata: Metadata) -> Output:
    if target.audience == "machine":
        return prepare_full(result, outer, metadata)
    return prepare_summary(result, outer, metadata)
