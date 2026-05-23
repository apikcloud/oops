# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: base.py — src/oops/output/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from oops.output.layout import Output

Target = Literal["console", "json"]


class OutputFormatter(ABC):
    """Shared contract for all command formatters.

    Carries `target` so the command knows which presenter to call,
    and defines the stable methods (`error`, `success`) that have the
    same semantics across every command.

    The `render` method is intentionally NOT defined here: each command
    has its own typed signature (e.g. AnalyzeFormatter.render(outer, modules)).
    """

    target: Target = "console"

    @abstractmethod
    def render(
        self,
        output: Output,
    ) -> None:
        """Render the final result.

        Args:
            outer: top-level Result holding global warnings/errors.
            items: list of dicts already prepared by the presenter.
                The shape depends on `self.target` — the command calls
                the matching presenter function before invoking render.
        """

    @abstractmethod
    def error(self, message: str, code: int = 1) -> None:
        """Report a fatal error. Must write to stderr."""

    @abstractmethod
    def success(self, message: str) -> None:
        """Report a successful operation."""
