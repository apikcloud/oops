from __future__ import annotations

import csv
import io
import sys

from oops.core.compat import Dict, Type
from oops.core.exceptions import get_error_console
from oops.core.paths import TEMPLATES
from oops.output.base import OutputFormatter, RenderTarget, SiteFormatter
from oops.output.layout import MetricsLayout, MinimalLayout, Output, SimpleSummaryLayout, SummaryLayout
from oops.output.serializers import to_json_string
from oops.utils.render import (
    conclude,
    counter_rule,
    error_section,
    get_console,
    make_table,
    metrics_grid,
    metrics_panel,
    print_error,
    print_result,
    print_warning,
    rule,
    warning_section,
)

MAX_COLUMNS = 6

FormatterRegistry = Dict[str, Type[OutputFormatter]]


class RichFormatter(OutputFormatter):
    """Base class for human-readable Rich console formatters."""

    target = RenderTarget(audience="human", verbosity="full")
    console = get_console()

    def error(self, message: str, code: int = 1) -> None:
        pass

    def success(self, message: str) -> None:
        pass


# Dans formatters.py


class PreCommitFormatter(OutputFormatter):
    """Minimal output for pre-commit hooks.

    Colored, concise, no table layout. Errors/warnings in stderr.
    """

    target = RenderTarget(audience="human", verbosity="summary")
    console = get_error_console()

    def render(self, output: "Output[MinimalLayout]") -> None:
        data = output.unwrap

        # Warnings (stderr)
        if data.warnings:
            for message in data.warnings:
                print_warning(message)

        # Errors (stderr)
        if data.errors:
            for message in data.errors:
                print_error(message)

        self.console.rule("", style="dim")
        print_result(data.status, data.message)

    def error(self, message: str, code: int = 1) -> None:
        pass

    def success(self, message: str) -> None:
        pass


class SummaryConsoleFormatter(RichFormatter):
    """Human-readable Rich console output for addons list and analyze."""

    def render(self, output: "Output[SummaryLayout]") -> None:

        data = output.unwrap

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

        data = output.unwrap

        rule(data.title)
        self.console.print()

        table = make_table(title=None, columns=data.table.columns, rows=data.table.rows, expand=True)
        panel = metrics_panel(data.panel.title, data.panel.values)

        # automatic ratio based on the number of columns
        # TODO: check whether this is a good idea
        ratios = [2, 1] if len(data.table.columns) <= MAX_COLUMNS else [3, 1]

        self.console.print(metrics_grid(table, panel, ratios=ratios))

        # TODO: improve this
        if data.info:
            for info in data.info:
                self.console.print()
                self.console.print(info)

        if data.warnings:
            self.console.print()
            warning_section(data.warnings)

        if data.errors:
            self.console.print()
            error_section(data.errors)

        self.console.print()
        conclude(data.conclusion.status, data.conclusion.message)


class MetricsConsoleFormatter(RichFormatter):
    """Human-readable Rich console output for project show."""

    def render(self, output: "Output[MetricsLayout]") -> None:

        data = output.unwrap

        rule(data.title)

        panels = [metrics_panel(panel.title, panel.values) for panel in data.panels]
        self.console.print()
        self.console.print(metrics_grid(*panels))

        if data.warnings:
            warning_section(data.warnings)

        conclude(data.conclusion.status, data.conclusion.message)


class HtmlFormatter(OutputFormatter):
    target = RenderTarget(audience="machine", verbosity="full")
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
    template = "analyze_v4.html"


class AddonsReportFormatter(HtmlFormatter):
    template = "list.html"


class DependsReportFormatter(HtmlFormatter):
    template = "depends_v4.html"


class ReleasesReportFormatter(HtmlFormatter):
    template = "releases.html"


class MarkdownSiteFormatter(SiteFormatter):
    """Render the DocModel as a multi-file Markdown site.

    Produces ``index.md``, one ``modules/<name>.md`` per module and one
    ``models/<bare>.md`` per bare model (aggregating every contributing module).
    Audit pages are added by Phase 4.
    """

    def render_site(self, output: "Output[dict]") -> Dict[str, str]:
        from oops.output.markdown.pages import (
            build_audit_index,
            build_audit_overrides,
            build_audit_views,
            build_index,
            build_model,
            build_module,
        )

        dm = output.layout
        files: Dict[str, str] = {"index.md": build_index(dm)}

        for mod in dm.get("modules", []):
            files[f"modules/{mod['module']}.md"] = build_module(dm, mod)

        for bare, entry in dm.get("models_by_bare", {}).items():
            files[entry["page"]] = build_model(dm, bare, entry)

        files["audit/index.md"] = build_audit_index(dm)
        files["audit/overrides.md"] = build_audit_overrides(dm)
        files["audit/views.md"] = build_audit_views(dm)

        return files


class JsonFormatter(OutputFormatter):
    """Machine-readable JSON output."""

    target = RenderTarget(audience="machine", verbosity="full")

    def render(self, output: Output[dict]) -> str:
        data = output.unwrap

        assert output.metadata is not None
        data = {**data, "metadata": output.metadata.to_dict()}

        return to_json_string(data)

    def error(self, message: str, code: int = 1) -> None:
        print(to_json_string({"error": message, "code": code}), file=sys.stderr)

    def success(self, message: str) -> None:
        print(to_json_string({"success": True, "message": message}))


class CsvFormatter(OutputFormatter):
    """Machine-readable CSV output (unimplemented — emits empty body)."""

    target = RenderTarget(audience="machine", verbosity="full")

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
