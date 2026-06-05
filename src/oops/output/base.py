# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: base.py — src/oops/output/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from oops.core.compat import Generic, Optional, TypeVar
from oops.core.metadata import Metadata
from oops.core.models import HasStatus, Result
from oops.output.layout import Layout, Output

D = TypeVar("D")  # data type for the simple case
T = TypeVar("T", bound=HasStatus)  # anything with ok/warnings/errors


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


class SiteFormatter(OutputFormatter):
    """Base for formatters that emit a multi-file site instead of one string.

    A site is N files, not a single rendered string, so the inherited
    single-string ``render`` returns ``None`` (sites never go through the
    ``deliver``/``write_output`` path) and ``render_site`` returns a
    ``{relative_path: content}`` tree delivered by ``deliver_site``.
    """

    target = RenderTarget(audience="machine", verbosity="full")

    def render(self, output: Output) -> Optional[str]:  # noqa: ARG002 - sites use render_site
        return None

    @abstractmethod
    def render_site(self, output: Output) -> "dict[str, str]":
        """Return the site as a mapping of relative path → file content."""

    def error(self, message: str, code: int = 1) -> None:
        import sys

        print(f"Error ({code}): {message}", file=sys.stderr)

    def success(self, message: str) -> None:
        pass


class Presenter(Generic[T]):
    """Base presenter dispatching on a two-axis RenderTarget."""

    def prepare(self, result: T, target: RenderTarget, metadata: Metadata | None = None) -> Output:
        if target.audience == "machine":
            layout = self.to_machine_summary(result) if target.verbosity == "summary" else self.to_machine(result)
        else:
            layout = self.to_human_summary(result) if target.verbosity == "summary" else self.to_human(result)

        return Output(layout=layout, metadata=metadata)

    def to_human(self, result: T) -> Layout:
        raise NotImplementedError

    def to_human_summary(self, result: T) -> Layout:
        return self.to_human(result)

    def to_machine(self, result: T) -> dict:
        raise NotImplementedError

    def to_machine_summary(self, result: T) -> dict:
        return self.to_machine(result)


class SimplePresenter(Presenter[Result[D]], Generic[D]):
    """Presenter for commands producing a single Result[D].

    Provides a default machine serialization. Multi-result commands
    (using ResultCollection) extend Presenter directly and define to_machine.
    """

    def to_machine(self, result: Result[D]) -> dict:
        return {"warnings": result.warnings, "data": result.data}
