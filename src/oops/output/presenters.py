# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: presenters.py — src/oops/output/presenters.py


from __future__ import annotations

from collections import Counter

from oops.core.checks import CheckOutcome
from oops.core.models import Result, ResultCollection, Stat, StatGroup
from oops.output.base import Presenter
from oops.output.layout import (
    ConclusionBlock,
    MinimalLayout,
    SimpleSummaryLayout,
    TableBlock,
    statgroup_to_panel,
)
from oops.utils.render import colorize_diff, colorize_from, render_boolean

COLOR_STATUS = {
    "failed": "red",
    "passed": "green",
    "skipped": "dim gray50",
}


def _build_row(result: Result[CheckOutcome]) -> list[str]:
    data = result.unwrap

    data.items.sort()
    details = "\n".join(colorize_diff(item) for item in data.items) + "\n" if len(data) else "--"

    return [
        data.label,
        render_boolean(data.active),
        colorize_from(data.status, COLOR_STATUS),
        details,
    ]


def _build_metrics(items):
    count = Counter(item.data.status for item in items)

    return StatGroup(
        name="summary",
        label="Summary",
        values=[
            Stat(name="total", label="Total", value=len(items)),
            Stat(name="passed", label="Passed", value=count["passed"]),
            Stat(name="skipped", label="Skipped", value=count["skipped"]),
            Stat(name="failed", label="Failed", value=count["failed"]),
        ],
    )


def _conclusion(results: "ResultCollection[CheckOutcome]") -> str:
    return "Check completed without errors" if results.ok else "Check failed"


class DefaultCheckPresenter(Presenter[ResultCollection[CheckOutcome]]):
    def to_machine(self, results: "ResultCollection[CheckOutcome]") -> dict:

        results.aggregate()
        return {
            "data": [result.unwrap.to_dict() for result in results],
            "warnings": results.warnings,
            "errors": results.errors,
        }

    def to_human_summary(self, results: "ResultCollection[CheckOutcome]") -> MinimalLayout:

        results.aggregate()
        results.warnings.sort()
        results.errors.sort()

        return MinimalLayout(
            status=results.ok,
            message=_conclusion(results),
            warnings=results.warnings,
            errors=results.errors,
        )

    def to_human(self, results: "ResultCollection[CheckOutcome]") -> SimpleSummaryLayout:
        items = results.unwrap

        metrics = _build_metrics(items)

        table = TableBlock(
            title="",
            columns=[
                ("Name", "brand.primary", "left"),
                ("Active", "dim", "left"),
                ("Status", "brand.primary", "left"),
                ("Item(s)", "dim", "left"),
            ],
            rows=[_build_row(result) for result in items],
        )

        panel = statgroup_to_panel(metrics)

        results.aggregate()

        return SimpleSummaryLayout(
            title=results.title,
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(results.ok, _conclusion(results)),
            warnings=results.warnings,
            # errors=results.errors,
        )
