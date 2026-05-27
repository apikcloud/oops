# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/depends/presenters/show.py

from __future__ import annotations

from oops.core.compat import TYPE_CHECKING
from oops.core.models import Result
from oops.output.layout import Output

if TYPE_CHECKING:
    from oops.output.base import RenderTarget


def prepare_full(result: "Result[list]", outer: "Result[None]", stats: dict) -> "Output[dict]":
    return Output(
        {
            "warnings": outer.warnings,
            "stats": stats,
            "addons": result.data,
        }
    )


def prepare(result: "Result[list]", outer: "Result[None]", target: RenderTarget, *, stats: dict) -> Output:
    # depends show has only machine targets (json/html); both use the dict layout.
    return prepare_full(result, outer, stats)
