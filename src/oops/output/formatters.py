from __future__ import annotations

import csv
import io
import sys

from oops.core.compat import Dict, Type
from oops.core.paths import TEMPLATES
from oops.output.base import OutputFormatter
from oops.output.layout import MetricsLayout, Output, SimpleSummaryLayout, SummaryLayout
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

FormatterRegistry = Dict[str, Type[OutputFormatter]]


class RichFormatter(OutputFormatter):
    """Base class for human-readable Rich console formatters."""

    target = "human"
    console = get_console()

    def error(self, message: str, code: int = 1) -> None:
        pass

    def success(self, message: str) -> None:
        pass


class SummaryConsoleFormatter(RichFormatter):
    """Human-readable Rich console output for addons list and analyze."""

    def render(self, output: "Output[SummaryLayout]") -> None:

        data = output.layout
        assert data

        self.console.print(data.title)

        if data.warnings:
            warning_section(data.warnings)

        for section in data.sections:
            rule(section.title)

            if section.warnings:
                warning_section(section.warnings)

            panels = [metrics_panel(panel.title, panel.values) for panel in section.panels]
            self.console.print()
            self.console.print(metrics_grid(*panels))

            if section.info:
                for info in section.info:
                    self.console.print()
                    self.console.print(info)

            for table in section.tables:
                self.console.print()
                if table.counter:
                    counter_rule(table.title, table.counter)
                else:
                    rule(table.title)

                self.console.print(make_table(title=None, columns=table.columns, rows=table.rows, expand=True))
                self.console.print()

        conclude(data.conclusion.status, data.conclusion.message)


class SimpleSummaryConsoleFormatter(RichFormatter):
    def render(self, output: "Output[SimpleSummaryLayout]") -> None:

        data = output.layout
        assert data

        rule(data.title)
        self.console.print()

        table = make_table(title=None, columns=data.table.columns, rows=data.table.rows, expand=True)
        panel = metrics_panel(data.panel.title, data.panel.values)

        self.console.print(metrics_grid(table, panel, ratios=[2, 1]))

        # TODO: improve this
        if data.info:
            for info in data.info:
                self.console.print()
                self.console.print(info)

        if data.warnings:
            warning_section(data.warnings)

        conclude(data.conclusion.status, data.conclusion.message)


class MetricsConsoleFormatter(RichFormatter):
    """Human-readable Rich console output for project show."""

    def render(self, output: "Output[MetricsLayout]") -> None:

        data = output.layout
        assert data

        rule(data.title)

        panels = [metrics_panel(panel.title, panel.values) for panel in data.panels]
        self.console.print()
        self.console.print(metrics_grid(*panels))

        if data.warnings:
            warning_section(data.warnings)

        conclude(data.conclusion.status, data.conclusion.message)


class HtmlFormatter(OutputFormatter):
    target = "machine"
    template: str

    def render(self, output: "Output[dict]") -> str:
        template = (TEMPLATES / self.template).read_text()
        payload = to_json_string(output.layout)
        return template.replace("__REPORT_DATA__", payload)

    def error(self, message: str, code: int = 1) -> None:
        # HTML has no meaningful inline error rendering — delegate to stderr.
        import sys

        print(f"Error ({code}): {message}", file=sys.stderr)

    def success(self, message: str) -> None:
        pass


class AnalysisReportFormatter(HtmlFormatter):
    template = "analyze.html"


class AddonsReportFormatter(HtmlFormatter):
    template = "list.html"


class DependsReportFormatter(HtmlFormatter):
    template = "depends_v4.html"


class ReleasesReportFormatter(HtmlFormatter):
    template = "releases.html"


class JsonFormatter(OutputFormatter):
    """Machine-readable JSON output."""

    target = "machine"

    def render(self, output: Output[dict]) -> str:
        data = output.layout
        assert data

        return to_json_string(data)

    def error(self, message: str, code: int = 1) -> None:
        print(to_json_string({"error": message, "code": code}), file=sys.stderr)

    def success(self, message: str) -> None:
        print(to_json_string({"success": True, "message": message}))


class CsvFormatter(OutputFormatter):
    """Machine-readable CSV output (unimplemented — emits empty body)."""

    target = "machine"

    def render(self, output: Output[dict]) -> str:
        rows = output.layout
        assert rows

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        # click.echo(buf.getvalue(), nl=False)

        # TODO: CsvFormatter unimplemented — emits an empty body until finished.
        return ""

    def error(self, message: str, code: int = 1) -> None:
        print(to_json_string({"error": message, "code": code}), file=sys.stderr)

    def success(self, message: str) -> None:
        print(to_json_string({"success": True, "message": message}))
