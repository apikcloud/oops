# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from __future__ import annotations

from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import (
    ConclusionBlock,
    MetricsPanelBlock,
    SimpleSummaryLayout,
    TableBlock,
)

ORIGIN_ICON = {"custom": "●", "oca": "◎", "third-party": "○"}


class AnalyzePresenter(SimplePresenter[dict]):
    """Presenter for `oops migrate analyze`."""

    def to_human(self, result: Result[dict]) -> SimpleSummaryLayout:
        data = result.unwrap
        metrics = data["metrics"]
        modules = data["modules"]

        rows = [
            [
                name,
                f"{ORIGIN_ICON.get(ms.origin.kind, '?')} {ms.origin.kind}",
                ms.origin.repo or "—",
                str(len(ms.depends_on)),
                "✓" if ms.upstream_available else ("?" if ms.upstream_available is None else "✗"),
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
                ("Upstream", "dim", "left"),
            ],
            rows=rows,
        )

        panel = MetricsPanelBlock(
            title="Metrics",
            values=[
                ["custom", str(metrics["custom"])],
                ["oca", str(metrics["oca"])],
                ["third-party", str(metrics["third_party"])],
            ],
        )

        conclusion_msg = (
            f"state.yml written — {metrics['total']} modules "
            f"({metrics['custom']} custom, {metrics['oca']} OCA, "
            f"{metrics['third_party']} third-party)"
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
        return {
            "source_ref": data["source_ref"],
            "state_path": data["state_path"],
            "metrics": data["metrics"],
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
                for name, ms in data["modules"].items()
            },
            "warnings": result.warnings,
        }
