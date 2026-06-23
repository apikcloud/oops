# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: helper.py — src/oops/output/helper.py


# Generic presenter + renderer for simple list-based commands.

from __future__ import annotations

from oops.core.compat import Optional
from oops.core.metadata import Metadata
from oops.core.models import Plan, Result, Rows
from oops.output.formatters import SimpleSummaryConsoleFormatter, StepConsoleFormatter
from oops.output.layout import (
    ConclusionBlock,
    MetricsPanelBlock,
    OnePanelLayout,
    Output,
    SimpleSummaryLayout,
    TableBlock,
)
from oops.utils.render import colorize_from

# Colour per action kind. Central place to tune plan presentation.
KIND_COLORS = {
    "available": "cyan",
    "selected": "green",
    "rename": "green",
    "rewrite": "green",
    "moved": "green",
    "promote": "green",
    "demote": "yellow",
    "skipped": "yellow",
    "nothing to do": "gray50",
    "step": "dim",
    "blocked": "red",
}


def prepare(
    result: Result[Rows],
    outer: Result,
    metadata: "Optional[Metadata]" = None,
) -> Output[SimpleSummaryLayout]:
    """Build a SimpleSummaryLayout from a Rows result.

    Args:
        result: The data (columns, rows, metrics).
        outer: Global warnings/errors.
        metadata: Optional execution metadata.

    Returns:
        An Output ready for rendering.
    """
    data = result.unwrap

    assert data.columns is not None
    assert data.metrics is not None

    panel = MetricsPanelBlock(
        title="Metrics",
        values=[[str(k).capitalize(), str(v)] for k, v in data.metrics.items()],
    )

    layout = SimpleSummaryLayout(
        title=data.title,
        panel=panel,
        table=TableBlock(title="", columns=data.columns, rows=data.rows),
        conclusion=ConclusionBlock(
            status=outer.ok,
            message="Command successful" if outer.ok else "Command failed",
        ),
        warnings=outer.warnings,
        errors=outer.errors,
    )

    return Output(layout=layout, metadata=metadata)


def prepare_plan(plan: Plan, metadata: "Optional[Metadata]" = None) -> Output[OnePanelLayout]:
    """Render a Plan as a pre-execution table. Console-only, pre-commit.

    Not part of the Presenter/RenderTarget pipeline: a plan has a single
    output mode (human console, before execution), so the two-axis dispatch
    does not apply. The separation builder(data) / renderer(presentation)
    is preserved all the same.
    """

    columns = [
        ("From", "", "left"),
        ("To", "brand.primary", "left"),
        ("Detail", "dim", "left"),
        ("Status", "", "right"),
    ]

    rows = [
        [
            action.label,
            action.new or "",
            action.detail,
            colorize_from(action.kind, KIND_COLORS),
        ]
        for action in plan.actions
    ]

    # Empty outer: the plan has not executed → neutral conclusion.
    return Output(
        layout=OnePanelLayout(
            title=plan.title,
            table=TableBlock(title="", columns=columns, rows=rows),
        ),
        metadata=metadata,
    )


def render(
    result: Result[Rows],
    outer: Result,
    metadata: Optional[Metadata] = None,
) -> None:
    """Prepare and render immediately to console.

    Convenience function for commands that don't need flexibility.
    """
    output = prepare(result, outer, metadata=metadata)
    formatter = SimpleSummaryConsoleFormatter()
    formatter.render(output)


def render_plan(
    plan: Plan,
    metadata: Optional[Metadata] = None,
) -> None:
    """Render a plan table before user confirmation.

    Uses an empty outer so the embedded ConclusionBlock reflects
    no errors (the plan has not executed yet).
    """

    output = prepare_plan(plan, metadata=metadata)
    formatter = StepConsoleFormatter()
    formatter.render(output)


def render_and_raise(result: Result[Rows], outer: Result) -> None:
    """Render the result then raise OopsError if outer has errors."""
    render(result, outer)
    if not outer.ok:
        from oops.core.exceptions import OopsError

        raise OopsError("; ".join(outer.errors))
