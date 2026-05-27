# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — src/oops/commands/submodules/presenters/update.py

from __future__ import annotations

from oops.core.compat import TYPE_CHECKING, List, Optional
from oops.core.models import CommitInfo, Result, Stat, StatGroup, SubmoduleInfo
from oops.output.layout import (
    ConclusionBlock,
    Output,
    SimpleSummaryLayout,
    TableBlock,
    statgroup_to_panel,
)
from oops.utils.render import approximate_duration, format_date, render_boolean

if TYPE_CHECKING:
    from oops.output.base import RenderTarget


def _render_commit(commit: Optional[CommitInfo]) -> List[str]:
    if commit is None:
        return ["", "", ""]
    return [format_date(commit.date), str(commit.age), commit.sha]


def _render_row(row: SubmoduleInfo) -> List[str]:
    last_commit, age, sha = _render_commit(row.last_commit)
    return [
        row.name,
        row.url,
        row.branch or "",
        render_boolean(row.pull_request),
        last_commit,
        age,
        sha,
    ]


def _build_metrics(rows: "Optional[List[SubmoduleInfo]]") -> StatGroup:

    import statistics

    return StatGroup(
        name="metrics",
        label="Metrics",
        values=[
            Stat(name="total", label="Total", value=len(rows) if rows else 0),
            Stat(name="pull_request", label="PRs", value=sum(row.pull_request for row in rows) if rows else 0),
            Stat(
                name="average_age",
                label="Average Age",
                value=approximate_duration(int(statistics.mean(row.last_commit.age for row in rows if row.last_commit)))
                if rows
                else 0,
            ),
            Stat(
                name="oldest",
                label="Oldest",
                value=approximate_duration(max(row.last_commit.age for row in rows if row.last_commit)) if rows else 0,
            ),
        ],
    )


def prepare_full(result: Result[List[SubmoduleInfo]], outer: "Result[None]") -> "Output[dict]":
    return Output(
        {
            "warnings": outer.warnings,
            "submodules": [row.to_dict() for row in result.data] if result.data else [],
            "metrics": _build_metrics(result.data).to_dict(),
        }
    )


def prepare_summary(result: "Result[List[SubmoduleInfo]]", outer: "Result[None]") -> Output:
    rows = result.data
    if rows is None:
        rows = []

    metrics = _build_metrics(rows)

    table = TableBlock(
        title="",
        columns=[
            ("Name", "brand.primary", "left"),
            ("Url", "dim", "left"),
            ("Branch", "brand.primary", "left"),
            ("PR", "dim", "left"),
            ("Last Commit", "dim", "left"),
            ("Age", "green", "right"),
            ("SHA", "dim", "left"),
        ],
        rows=[_render_row(row) for row in rows],
    )

    panel = statgroup_to_panel(metrics)

    all_ok = bool(rows)

    return Output(
        SimpleSummaryLayout(
            title="Submodules",
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(all_ok, "Report done" if all_ok else "Something wrongs"),
            warnings=outer.warnings,
            errors=outer.errors,
        )
    )


def prepare(results: "Result[List[SubmoduleInfo]]", outer: "Result[None]", target: RenderTarget) -> Output:
    """Single entry point — dispatches based on the formatter target."""
    if target.audience == "machine":
        return prepare_full(results, outer)
    return prepare_summary(results, outer)
