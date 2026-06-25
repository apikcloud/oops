# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: apply.py — src/oops/commands/migrate/presenters/apply.py

from __future__ import annotations

from collections import Counter

from oops.core.models import Result, Stat, StatGroup
from oops.output.base import SimplePresenter
from oops.output.layout import (
    ConclusionBlock,
    MinimalLayout,
    SimpleSummaryLayout,
    TableBlock,
    statgroup_to_panel,
)
from oops.utils.render import colorize_from

COLOR_STATUS = {
    "done": "green",
    "failed": "red",
    "skipped": "yellow",
    "pending": "dim",
}

COLOR_ACTION = {
    "port": "brand.primary",
    "pull": "cyan",
    "drop": "dim",
}


def _counts(result: "Result[dict]") -> "tuple[bool, str, Counter]":
    data = result.unwrap
    rows = data.get("rows", [])
    dry_run = data.get("dry_run", False)
    counts = Counter(row[3] for row in rows)  # row[3] = status
    all_ok = result.ok and not counts["failed"]

    if dry_run:
        msg = f"Dry run — {len(rows)} module(s) would be processed"
    elif counts["failed"]:
        msg = f"{counts['failed']} module(s) failed"
    elif counts["done"]:
        msg = f"{counts['done']} module(s) applied successfully"
    else:
        msg = "Nothing applied"

    return all_ok, msg, counts


class ApplyPresenter(SimplePresenter[dict]):
    def to_human(self, result: "Result[dict]") -> SimpleSummaryLayout:
        data = result.unwrap
        rows = data.get("rows", [])
        all_ok, msg, counts = _counts(result)

        # Columns: Name | Action | Branch | Status | Tools | Error
        table = TableBlock(
            title="",
            columns=[
                ("Module", "brand.primary", "left"),
                ("Action", "dim", "left"),
                ("Branch", "dim", "left"),
                ("Status", "dim", "center"),
                ("Tools", "dim", "left"),
                ("Error", "dim", "left"),
            ],
            rows=[
                [
                    row[0],
                    colorize_from(row[1], COLOR_ACTION),
                    row[2],
                    colorize_from(row[3], COLOR_STATUS),
                    row[4],
                    row[5] if row[5] != "—" else "",
                ]
                for row in rows
            ],
        )

        metrics = StatGroup(
            name="summary",
            label="Summary",
            values=[
                Stat(name="total", label="Total", value=len(rows)),
                Stat(name="done", label="Done", value=counts["done"]),
                Stat(name="failed", label="Failed", value=counts["failed"]),
                Stat(name="skipped", label="Skipped", value=counts["skipped"]),
            ],
        )

        return SimpleSummaryLayout(
            title=data.get("cmd", "Migration apply"),
            table=table,
            panel=statgroup_to_panel(metrics),
            conclusion=ConclusionBlock(all_ok, msg),
            warnings=result.warnings,
            errors=result.errors,
        )

    def to_human_summary(self, result: "Result[dict]") -> MinimalLayout:
        all_ok, msg, _ = _counts(result)
        return MinimalLayout(
            status=all_ok,
            message=msg,
            warnings=result.warnings,
            errors=result.errors,
        )

    def to_machine(self, result: "Result[dict]") -> dict:
        data = result.unwrap
        return {
            "cmd": data.get("cmd"),
            "dry_run": data.get("dry_run", False),
            "metrics": data.get("metrics", {}),
            "modules": [
                {
                    "name": row[0],
                    "action": row[1],
                    "branch": row[2],
                    "status": row[3],
                    "tools_run": [t for t in row[4].split(", ") if t != "—"],
                    "error": row[5] if row[5] != "—" else None,
                }
                for row in data.get("rows", [])
            ],
            "warnings": result.warnings,
            "errors": result.errors,
        }
