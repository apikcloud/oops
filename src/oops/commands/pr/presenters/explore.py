# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from __future__ import annotations

from collections import Counter
from dataclasses import asdict

from oops.core.models import PullRequest, Result, Stat, StatGroup
from oops.output.base import SimplePresenter
from oops.output.layout import (
    ConclusionBlock,
    SimpleSummaryLayout,
    TableBlock,
    statgroup_to_panel,
)
from oops.utils.render import colorize
from oops_engine.compat import List

COLOR_STATUS = {
    "open": "green",
    "closed": "yellow",
    "merged": "yellow",
}


def _build_metrics(rows: "List[PullRequest]") -> StatGroup:
    counter = Counter(pr.state for pr in rows)
    return StatGroup(
        name="metrics",
        label="Metrics",
        values=[Stat(name="total", label="Total", value=len(rows))]
        + [Stat(name=k, label=k.capitalize(), value=v) for k, v in counter.items()],
    )


def _render_row(pr: PullRequest) -> "List[str]":
    return [
        f"[link={pr.url}]#{pr.number}[/link]",
        pr.title,
        pr.base,
        pr.author or "",
        colorize(pr.state, COLOR_STATUS.get(pr.state, "dim")),
    ]


class ExplorePresenter(SimplePresenter[List[PullRequest]]):
    def to_machine(self, result: Result[List[PullRequest]]) -> dict:
        rows = result.unwrap
        return {
            "warnings": result.warnings,
            "pull_requests": [asdict(pr) for pr in rows],
            "metrics": _build_metrics(rows).to_dict(),
        }

    def to_human(self, result: Result[List[PullRequest]]) -> SimpleSummaryLayout:
        rows = result.unwrap
        metrics = _build_metrics(rows)
        table = TableBlock(
            title="",
            columns=[
                ("#", "dim", "right"),
                ("Title", "brand.primary", "left"),
                ("Base", "dim", "left"),
                ("Author", "dim", "left"),
                ("Status", "green", "right"),
            ],
            rows=[_render_row(pr) for pr in rows],
        )
        return SimpleSummaryLayout(
            title="Pull Requests",
            table=table,
            panel=statgroup_to_panel(metrics),
            conclusion=ConclusionBlock(result.ok, "Report done" if result.ok else "Something went wrong"),
            warnings=result.warnings,
            errors=result.errors,
        )
