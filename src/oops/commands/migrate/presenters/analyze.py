# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from __future__ import annotations

from oops.commands.migrate.common import ModuleState
from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import (
    ConclusionBlock,
    MetricsPanelBlock,
    SimpleSummaryLayout,
    TableBlock,
)

ORIGIN_ICON = {"custom": "●", "oca": "◎", "third-party": "○"}


def _upstream_cell(ms: ModuleState) -> str:
    """Return a Rich-markup-colored upstream status symbol."""
    if ms.origin.kind == "custom":
        return "[dim]—[/]"
    if ms.upstream_available is None:
        return "[dim]?[/]"
    if ms.upstream_available:
        return "[green]✓[/]"
    if ms.upstream_prs:
        return "[yellow]~ PR[/]"
    return "[red]✗[/]"


def _effort_metrics(modules: dict) -> dict[str, int]:
    """Compute effort-oriented counts across all modules."""
    to_pull = 0
    in_pr = 0
    to_port = 0
    not_probed = 0
    for ms in modules.values():
        if ms.origin.kind == "custom":
            to_port += 1
        elif ms.upstream_available is True:
            to_pull += 1
        elif ms.upstream_available is False:
            if ms.upstream_prs:
                in_pr += 1
            else:
                to_port += 1
        else:
            not_probed += 1
    return {"to_pull": to_pull, "in_pr": in_pr, "to_port": to_port, "not_probed": not_probed}


class AnalyzePresenter(SimplePresenter[dict]):
    """Presenter for `oops migrate analyze`."""

    def to_human(self, result: Result[dict]) -> SimpleSummaryLayout:
        data = result.unwrap
        metrics = data["metrics"]
        modules = data["modules"]
        effort = _effort_metrics(modules)

        rows = [
            [
                name,
                f"{ORIGIN_ICON.get(ms.origin.kind, '?')} {ms.origin.kind}",
                ms.origin.repo or "—",
                str(len(ms.depends_on)),
                _upstream_cell(ms),
            ]
            for name, ms in sorted(modules.items())
        ]

        table = TableBlock(
            title="Modules",
            columns=[
                ("Module", "brand.primary", "left"),
                ("Origin", "dim", "left"),
                ("Repo", "dim", "left"),
                ("Deps", "green", "right"),
                ("Upstream", "", "left"),
            ],
            rows=rows,
        )

        panel_values = [
            ["custom", str(metrics["custom"])],
            ["oca", str(metrics["oca"])],
            ["third-party", str(metrics["third_party"])],
            ["", ""],
            ["to pull", f"[green]{effort['to_pull']}[/]"],
            ["in PR", f"[yellow]{effort['in_pr']}[/]"],
            ["to port", f"[red]{effort['to_port']}[/]"],
        ]
        if effort["not_probed"]:
            panel_values.append(["not probed", f"[dim]{effort['not_probed']}[/]"])

        panel = MetricsPanelBlock(title="Effort", values=panel_values)

        conclusion_msg = (
            f"state.yml written — {metrics['total']} modules "
            f"({metrics['custom']} custom, {metrics['oca']} OCA, "
            f"{metrics['third_party']} third-party) · "
            f"{effort['to_pull']} to pull, {effort['in_pr']} in PR, "
            f"{effort['to_port']} to port"
        )

        return SimpleSummaryLayout(
            title=data["cmd"],
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(result.ok, conclusion_msg),
            warnings=result.warnings,
            errors=result.errors,
        )

    def to_machine(self, result: Result[dict]) -> dict:
        data = result.unwrap
        modules = data["modules"]
        return {
            "source_ref": data["source_ref"],
            "state_path": data["state_path"],
            "metrics": data["metrics"],
            "effort": _effort_metrics(modules),
            "modules": {
                name: {
                    "origin": {
                        "kind": ms.origin.kind,
                        "repo": ms.origin.repo,
                        "ref": ms.origin.ref,
                    },
                    "depends_on": ms.depends_on,
                    "upstream_available": ms.upstream_available,
                    "upstream_prs": ms.upstream_prs,
                }
                for name, ms in modules.items()
            },
            "warnings": result.warnings,
        }
