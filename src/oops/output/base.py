# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: base.py — src/oops/output/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from oops.core.compat import Optional
from oops.output.layout import Output


@dataclass
class RenderTarget:
    audience: Literal["human", "machine"]
    verbosity: Literal["full", "summary"] = "full"


class OutputFormatter(ABC):
    """Shared contract for all command formatters.

    Carries `target` so the command knows which presenter to call,
    and defines the stable methods (`error`, `success`) that have the
    same semantics across every command.

    The `render` method is intentionally NOT defined here: each command
    has its own typed signature (e.g. AnalyzeFormatter.render(outer, modules)).
    """

    target = RenderTarget(audience="human", verbosity="summary")

    @abstractmethod
    def render(self, output: Output) -> Optional[str]:
        """Render `output`.

        Human formatters print via Rich and return None.
        Machine formatters return a string to be delivered by a sink.
        """

    @abstractmethod
    def error(self, message: str, code: int = 1) -> None:
        """Report a fatal error. Must write to stderr."""

    @abstractmethod
    def success(self, message: str) -> None:
        """Report a successful operation."""
