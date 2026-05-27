# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — src/oops/commands/odoo/presenters/update.py

from __future__ import annotations

from oops.core.compat import TYPE_CHECKING, Dict, List
from oops.core.metadata import Metadata
from oops.core.models import Result, StatGroup
from oops.output.layout import (
    ConclusionBlock,
    Output,
    SimpleSummaryLayout,
    TableBlock,
    statgroup_to_panel,
)

if TYPE_CHECKING:
    from oops.output.base import RenderTarget


def prepare_full(
    result: "Result[List[Dict]]",
    outer: "Result[None]",
    stats: StatGroup,
    metadata: Metadata,
) -> "Output[dict]":
    return Output(
        {
            "metadata": metadata.to_dict(),
            "warnings": outer.warnings,
            "sources": result.data if result.data else [],
            "counters": stats.to_dict(),
        }
    )


def prepare_summary(
    result: "Result[List[Dict]]",
    outer: "Result[None]",
    stats: StatGroup,
    metadata: Metadata,
) -> "Output[SimpleSummaryLayout]":
    data = result.data
    assert data

    table = TableBlock(
        title="",
        columns=[
            ("Version", "brand.primary", "left"),
            ("Community", "dim", "left"),
            ("Enterprise", "dim", "left"),
            ("Themes", "dim", "left"),
        ],
        rows=[[row["version"], row["community"], row["enterprise"], row["themes"]] for row in data],
    )

    all_ok = not result.errors
    out = Output(
        SimpleSummaryLayout(
            title="Odoo Sources",
            table=table,
            panel=statgroup_to_panel(stats),
            conclusion=ConclusionBlock(all_ok, "All done" if all_ok else "Some repos failed"),
            warnings=outer.warnings,
        )
    )
    out.metadata = metadata
    return out


def prepare(
    result: "Result[List[Dict]]",
    outer: "Result[None]",
    stats: StatGroup,
    target: RenderTarget,
    metadata: Metadata,
) -> Output:
    if target.audience == "machine":
        return prepare_full(result, outer, stats, metadata)
    return prepare_summary(result, outer, stats, metadata)
