# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: vanilla.py — src/oops/commands/upgrade/presenters/vanilla.py

from __future__ import annotations

from oops.core.models import Result, Stat, StatGroup
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MinimalLayout, SimpleSummaryLayout, TableBlock, statgroup_to_panel
from oops.utils.render import colorize_from

COLOR_MATCHED_ORIGIN = {
    "core": "red",
    "enterprise": "red",
}


def _counts(result: "Result[dict]") -> "tuple[bool, str]":
    data = result.unwrap
    rows = data.get("rows", [])
    dry_run = data.get("dry_run", False)
    collisions = sum(1 for row in rows if row[3])
    all_ok = result.ok

    if dry_run:
        msg = f"Dry run — {len(rows)} module(s) would be removed"
    elif not rows:
        msg = "Nothing removed"
    elif collisions:
        msg = f"{len(rows)} module(s) removed, {collisions} flagged as a real Odoo module — see warnings"
    else:
        msg = f"{len(rows)} module(s) removed"

    return all_ok, msg


class VanillaPresenter(SimplePresenter[dict]):
    def to_human(self, result: "Result[dict]") -> SimpleSummaryLayout:
        data = result.unwrap
        rows = data.get("rows", [])
        all_ok, msg = _counts(result)

        # rows: [name, classification, load_index, matched_origin]
        table = TableBlock(
            title="",
            columns=[
                ("Module", "brand.primary", "left"),
                ("Classification", "dim", "left"),
                ("Load index", "dim", "right"),
                ("Matched origin", "dim", "left"),
            ],
            rows=[
                [
                    row[0],
                    row[1],
                    row[2],
                    colorize_from(row[3], COLOR_MATCHED_ORIGIN) if row[3] else "",
                ]
                for row in rows
            ],
        )

        collisions = sum(1 for row in rows if row[3])
        metrics = StatGroup(
            name="summary",
            label="Summary",
            values=[
                Stat(name="total", label="Total modules", value=len(rows)),
                Stat(
                    name="collisions",
                    label="Core/enterprise collisions",
                    value=collisions,
                    highlight=collisions > 0,
                ),
                Stat(name="branch", label="Branch", value=data.get("branch") or "—"),
                Stat(name="tag", label="Tag", value=data.get("tag") or "—"),
                Stat(name="script_path", label="Script path", value=data.get("script_path", "—")),
                Stat(name="kb_checked", label="KB checked", value="yes" if data.get("kb_checked") else "no"),
            ],
        )

        return SimpleSummaryLayout(
            title=data.get("cmd", "Upgrade vanilla"),
            table=table,
            panel=statgroup_to_panel(metrics),
            conclusion=ConclusionBlock(all_ok, msg),
            warnings=result.warnings,
            errors=result.errors,
        )

    def to_human_summary(self, result: "Result[dict]") -> MinimalLayout:
        all_ok, msg = _counts(result)
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
            "branch": data.get("branch"),
            "tag": data.get("tag"),
            "script_path": data.get("script_path"),
            "report_path": data.get("report_path"),
            "kb_checked": data.get("kb_checked", False),
            "modules": [
                {
                    "name": row[0],
                    "classification": row[1],
                    "load_index": row[2],
                    "matched_origin": row[3] or None,
                }
                for row in data.get("rows", [])
            ],
            "warnings": result.warnings,
            "errors": result.errors,
        }
