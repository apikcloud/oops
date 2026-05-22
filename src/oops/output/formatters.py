from __future__ import annotations

import sys

from oops.core.models import Result, SummaryView
from oops.output.base import OutputFormatter
from oops.output.serializers import to_json_string
from oops.utils.render import (
    conclude,
    counter_rule,
    get_console,
    make_table,
    metrics_grid,
    metrics_panel,
    rule,
    warning_section,
)


class AnalyzeFormatter(OutputFormatter):
    """Command-specific contract for the `example` command.

    Inherits `target`, `error`, `success` from OutputFormatter.
    Adds a typed `render` signature that matches what this command produces.

    Each command in family C defines its own contract — `render` signatures
    differ between commands and are not shared.
    """


class SummaryConsoleFormatter(OutputFormatter):
    """Human-readable Rich output for the `example` command.

    Receives dicts already prepared by `presenter.prepare_for_human()`.
    Has no knowledge of the domain dataclasses.
    """

    target = "summary"

    def render(self, result: "Result[SummaryView]") -> None:
        data = result.data

        assert data

        console = get_console()
        console.print(data.title)

        if data.warnings:
            warning_section(data.warnings)

        for section in data.sections:
            rule(section.title)

            if section.warnings:
                warning_section(section.warnings)

            panels = [metrics_panel(panel.title, panel.values) for panel in section.panels]
            console.print()
            console.print(metrics_grid(*panels))

            if section.info:
                for info in section.info:
                    console.print()
                    console.print(info)

            for table in section.tables:
                console.print()
                if table.counter:
                    counter_rule(table.title, table.counter)
                else:
                    rule(table.title)

                # console.print(make_table(title=None, columns=columns, rows=rows))
                # console.print()

                console.print(make_table(title=None, columns=table.columns, rows=table.rows, expand=True))
                console.print()

        conclude(data.conclusion.status, data.conclusion.message)

    def error(self, message: str, code: int = 1) -> None:
        # error(message, code)
        pass

    def success(self, message: str) -> None:
        # success(message)
        pass


class AnalyzeJsonFormatter(OutputFormatter):
    """Machine-readable JSON output for the `example` command.

    Receives dicts already prepared by `presenter.prepare_for_machine()`.
    Has no knowledge of the domain dataclasses.
    """

    target = "full"

    def render(self, result: Result) -> None:
        print(to_json_string(result.data))

    def error(self, message: str, code: int = 1) -> None:
        print(to_json_string({"error": message, "code": code}), file=sys.stderr)

    def success(self, message: str) -> None:
        print(to_json_string({"success": True, "message": message}))
