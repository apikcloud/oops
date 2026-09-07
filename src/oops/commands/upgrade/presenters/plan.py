# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from __future__ import annotations

from oops.commands.upgrade.common import ModulePlan
from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import (
    ConclusionBlock,
    MetricsPanelBlock,
    SimpleSummaryLayout,
    TableBlock,
)

ACTION_COLOR: dict[str, str] = {
    "pull": "green",
    "port": "yellow",
    "drop": "red",
}


def _action_cell(mp: ModulePlan) -> str:
    if not mp.action:
        return "[red]? (missing)[/]"
    color = ACTION_COLOR.get(mp.action, "")
    return f"[{color}]{mp.action}[/]" if color else mp.action


class PlanPresenter(SimplePresenter[dict]):
    """Presenter for `oops upgrade plan`."""

    def to_human(self, result: Result[dict]) -> SimpleSummaryLayout:
        data = result.unwrap
        metrics = data["metrics"]
        modules: dict[str, ModulePlan] = data["modules"]

        rows = [
            [
                name,
                _action_cell(mp),
                mp.origin.kind if mp.origin else "—",
                mp.origin.repo or "—" if mp.origin else "—",
                "[yellow]✎[/]" if mp.review else "",
            ]
            for name, mp in sorted(modules.items())
        ]

        table = TableBlock(
            title="Plan",
            columns=[
                ("Module", "brand.primary", "left"),
                ("Action", "", "left"),
                ("Origin", "dim", "left"),
                ("Repo", "dim", "left"),
                ("Review", "yellow", "left"),
            ],
            rows=rows,
        )

        panel = MetricsPanelBlock(
            title="Actions",
            values=[
                ["pull", f"[green]{metrics['pull']}[/]"],
                ["port", f"[yellow]{metrics['port']}[/]"],
                ["drop", f"[red]{metrics['drop']}[/]"],
                ["", ""],
                ["review", f"[yellow]{metrics['review']}[/]"],
            ],
        )

        is_first = data.get("is_first_run", False)
        if result.ok:
            action_word = "seeded" if is_first else "reconciled"
            msg = (
                f"plan.yml {action_word} — {metrics['total']} modules, "
                f"{metrics['review']} need review"
            )
        else:
            msg = f"plan.yml NOT written — {len(result.errors)} error(s)"

        return SimpleSummaryLayout(
            title=data["cmd"],
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(result.ok, msg),
            warnings=result.warnings,
            errors=result.errors,
        )

    def to_machine(self, result: Result[dict]) -> dict:
        data = result.unwrap
        modules: dict[str, ModulePlan] = data["modules"]
        return {
            "plan_path": data["plan_path"],
            "metrics": data["metrics"],
            "is_first_run": data.get("is_first_run", False),
            "modules": {
                name: {
                    "action": mp.action,
                    "origin": {
                        "kind": mp.origin.kind,
                        "repo": mp.origin.repo,
                    } if mp.origin else None,
                    "review": mp.review,
                }
                for name, mp in modules.items()
            },
            "warnings": result.warnings,
            "errors": result.errors,
        }
