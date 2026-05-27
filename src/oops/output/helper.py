# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: helper.py — src/oops/output/helper.py


# Generic presenter + renderer for simple list-based commands.

from __future__ import annotations

from oops.core.metadata import Metadata
from oops.core.models import Result, Rows
from oops.output.formatters import SimpleSummaryConsoleFormatter
from oops.output.layout import (
    ConclusionBlock,
    MetricsPanelBlock,
    Output,
    SimpleSummaryLayout,
    TableBlock,
)


def prepare(
    result: Result[Rows],
    outer: Result,
    metadata: Metadata | None = None,
) -> Output[SimpleSummaryLayout]:
    """Build a SimpleSummaryLayout from a Rows result.

    Args:
        result: The data (columns, rows, metrics).
        outer: Global warnings/errors.
        metadata: Optional execution metadata.

    Returns:
        An Output ready for rendering.
    """
    data = result.data
    assert data is not None
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


def render(
    result: Result[Rows],
    outer: Result,
    metadata: Metadata | None = None,
) -> None:
    """Prepare and render immediately to console.

    Convenience function for commands that don't need flexibility.
    """
    output = prepare(result, outer, metadata=metadata)
    formatter = SimpleSummaryConsoleFormatter()
    formatter.render(output)
