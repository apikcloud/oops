# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/project/presenters/show.py


from oops.core.models import Result
from oops.output.layout import ConclusionBlock, MetricsLayout, MetricsPanelBlock, Output


def prepare_full(result: Result[dict], outer: "Result[None]") -> "Output[dict]":
    assert result.data
    return Output(
        {
            "warnings": outer.warnings,
            "project": result.data["title"],
            "metrics": result.data["metrics"],
        }
    )


def prepare_summary(result: Result[dict], outer: "Result[None]") -> "Output[MetricsLayout]":

    data = result.data
    assert data

    metrics = [MetricsPanelBlock(k.capitalize(), v) for k, v in data["metrics"].items()]

    return Output(
        MetricsLayout(
            title=f"Project status - {data['project']}",
            panels=metrics,
            conclusion=ConclusionBlock(True, "Status report"),
            warnings=outer.warnings,
        )
    )


def prepare(results: "Result[dict]", outer: "Result[None]", target: str) -> Output:
    """Single entry point — dispatches based on the formatter target."""
    if target == "machine":
        return prepare_full(results, outer)
    return prepare_summary(results, outer)
