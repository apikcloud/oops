from __future__ import annotations

import sys

from oops.output.base import OutputFormatter
from oops.output.layout import Output, SummaryLayout
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


class SummaryConsoleFormatter(OutputFormatter):
    """Human-readable Rich output for the `example` command.

    Receives dicts already prepared by `presenter.prepare_for_human()`.
    Has no knowledge of the domain dataclasses.
    """

    target = "console"

    def render(self, output: "Output[SummaryLayout]") -> None:

        data = output.layout
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


class JsonFormatter(OutputFormatter):
    """Machine-readable JSON output for the `example` command.

    Receives dicts already prepared by `presenter.prepare_for_machine()`.
    Has no knowledge of the domain dataclasses.
    """

    target = "json"

    def render(self, output: Output) -> None:
        data = output.layout
        assert data

        print(to_json_string(data))

    def error(self, message: str, code: int = 1) -> None:
        print(to_json_string({"error": message, "code": code}), file=sys.stderr)

    def success(self, message: str) -> None:
        print(to_json_string({"success": True, "message": message}))
