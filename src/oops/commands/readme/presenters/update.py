# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — src/oops/commands/readme/presenters/update.py

from __future__ import annotations

from collections import Counter

from oops.core.models import Result, Stat, StatGroup
from oops.output.base import Presenter
from oops.output.layout import (
    ConclusionBlock,
    MinimalLayout,
    Output,
    SimpleSummaryLayout,
    TableBlock,
    statgroup_to_panel,
)
from oops.utils.render import colorize

COLOR_STATUS = {
    "failed": "red",
    "updated": "green",
    "no change": "dim",
}


def _get_status(result):

    rows = result.data.get("rows", [])
    dry_run = result.data.get("dry_run", False)
    status = Counter(row[1] for row in rows)
    has_update = bool(status["updated"])

    all_ok = result.ok and not status["failed"]

    if dry_run:
        conclusion_msg = "Dry run — README not modified"
    elif has_update:
        conclusion_msg = "README updated"
    elif all_ok:
        conclusion_msg = "README already up to date"
    else:
        conclusion_msg = "Command failed"

    return all_ok, conclusion_msg, status


class UpdatePresenter(Presenter[Result[dict]]):
    def to_human(self, result, outer) -> Output[SimpleSummaryLayout]:
        data = result.data
        assert data

        rows = data.get("rows", [])

        all_ok, conclusion_msg, status = _get_status(result, outer)

        def _colorize(status: str) -> str:
            return colorize(status, COLOR_STATUS.get(status, "dim"))

        table = TableBlock(
            title="",
            columns=[
                ("Section", "brand.primary", "left"),
                ("Status", "dim", "left"),
            ],
            rows=[[row[0], _colorize(row[1])] for row in rows],
        )

        metrics = StatGroup(
            name="summary",
            label="Summary",
            values=[
                Stat(
                    name="sections",
                    label="Sections",
                    value=len(rows),
                ),
                Stat(
                    name="updated",
                    label="Updated",
                    value=status["updated"],
                ),
                Stat(
                    name="failed",
                    label="Failed",
                    value=status["failed"],
                ),
            ],
        )

        return Output(
            SimpleSummaryLayout(
                title=data.get("cmd", "Update README"),
                table=table,
                panel=statgroup_to_panel(metrics),
                conclusion=ConclusionBlock(all_ok, conclusion_msg),
                warnings=outer.warnings,
                errors=outer.errors,
            )
        )

    def to_human_summary(self, result) -> Output[MinimalLayout]:
        all_ok, message, _ = _get_status(result)

        return Output(
            MinimalLayout(
                status=all_ok,
                message=message,
                warnings=result.warnings,
                errors=result.errors,
            ),
        )
