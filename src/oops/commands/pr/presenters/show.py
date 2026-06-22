# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/pr/presenters/show.py


from __future__ import annotations

from collections import Counter

from oops.core.compat import List
from oops.core.models import Result, Stat, StatGroup, SubmoduleInfo
from oops.output.base import SimplePresenter
from oops.output.layout import (
    ConclusionBlock,
    SimpleSummaryLayout,
    TableBlock,
    statgroup_to_panel,
)
from oops.utils.render import colorize

COLOR_STATUS = {
    "cancel": "red",
    "merged": "yellow",
    "open": "green",
    "closed": "yellow",
}


def _render_row(row: SubmoduleInfo) -> List[str]:

    pr = row.resolved_pr

    return [
        row.name,
        row.branch or "",
        str(pr.upstream) if pr else "",
        f"[link={pr.url}]#{pr.number}[/link]" if pr else "",
        colorize(pr.state, COLOR_STATUS.get(pr.state, "dim")) if pr else "",
    ]


def _build_metrics(rows: "List[SubmoduleInfo]") -> StatGroup:

    def _get_status(row):
        pr = row.resolved_pr
        return pr.state if pr else "unresolved"

    counter = Counter(_get_status(row) for row in rows)

    return StatGroup(
        name="metrics",
        label="Metrics",
        values=[
            Stat(name="total", label="Total", value=len(rows) if rows else 0),
        ]
        + [
            Stat(
                name=k,
                label=k.capitalize(),
                value=v,
            )
            for k, v in counter.items()
        ],
    )


class ShowPresenter(SimplePresenter[List[SubmoduleInfo]]):
    def to_machine(self, result: Result[List[SubmoduleInfo]]) -> dict:
        rows = result.unwrap

        return {
            "warnings": result.warnings,
            "submodules": [row.to_dict() for row in rows] or [],
            "metrics": _build_metrics(rows).to_dict(),
        }

    def to_human(self, result: Result[List[SubmoduleInfo]]) -> SimpleSummaryLayout:
        rows = result.unwrap

        metrics = _build_metrics(rows)

        table = TableBlock(
            title="",
            columns=[
                ("Name", "brand.primary", "left"),
                ("Branch", "dim", "left"),
                ("Upstream", "brand.primary", "left"),
                ("ID", "dim", "left"),
                ("Status", "green", "right"),
            ],
            rows=[_render_row(row) for row in rows],
        )

        panel = statgroup_to_panel(metrics)

        return SimpleSummaryLayout(
            title="Pull Requests",
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(result.ok, "Report done" if result.ok else "Something went wrong"),
            warnings=result.warnings,
            errors=result.errors,
        )
