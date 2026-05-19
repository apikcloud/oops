# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: render.py — oops/utils/render.py

from __future__ import annotations

import logging
import textwrap
from datetime import datetime
from typing import TYPE_CHECKING

import questionary
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.utils.compat import Any, List, Optional
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.theme import Theme
from tabulate import tabulate

_METHOD_COLUMNS: list[tuple[str, str]] = [
    ("COMPUTE METHODS", "Compute"),
    ("SELECTION METHODS", "Select"),
    ("DEFAULT METHODS", "Default"),
    ("ONCHANGE METHODS", "Onchange"),
    ("CONSTRAINT METHODS", "Constrain"),
    ("CRUD METHODS", "CRUD"),
    ("HELPER METHODS", "Helper"),
    ("ACTION METHODS", "Action"),
    ("BUSINESS METHODS", "Business"),
]

RICH_THEME = Theme(
    {
        "brand.bg": Style(color="#2e3548"),
        "brand.primary": Style(color="#505ba6"),
        "brand.dim": Style(color="#505ba6", dim=True),
    }
)


def get_console() -> Console:
    """Return a stdout-bound Rich Console.

    Created lazily on every call so pytest's ``capsys`` fixture (which
    monkey-patches ``sys.stdout`` after import time) captures the output.
    Rich caches ``self.file`` at ``Console.__init__``, so a module-level
    instance would bypass ``capsys``.
    """
    return Console(highlight=False, soft_wrap=False, theme=RICH_THEME)


def get_error_console() -> Console:
    """Return a stderr-bound Rich Console."""
    return Console(highlight=False, soft_wrap=False, theme=RICH_THEME, stderr=True)


def format_datetime(dt: datetime) -> str:
    """Format a datetime as a string using the configured datetime format.

    Args:
        dt: Datetime object to format.

    Returns:
        Formatted datetime string.
    """

    return dt.strftime(config.datetime_format)


def human_readable(raw: Any, sep: str = ", ", width: Optional[int] = None) -> str:
    """Convert a value to a human-readable string.

    Booleans become ``yes``/``no``; collections are joined; strings are optionally
    truncated to a maximum width.

    Args:
        raw: Value to render.
        sep: Separator used to join collection items. Defaults to ", ".
        width: If provided, truncate the result to this many characters. Defaults to None.

    Returns:
        Human-readable string representation of raw.
    """

    if isinstance(raw, bool):
        return "yes" if raw else "no"
    if isinstance(raw, (list, tuple, set)):
        return sep.join(map(str, raw))

    if width:
        return textwrap.shorten(raw, width=width, placeholder="...")

    return str(raw)


def render_boolean(raw: bool) -> str:
    """Render a boolean as a check symbol or an empty string.

    Args:
        raw: Boolean value to render.

    Returns:
        Configured check symbol if True, empty string if False.
    """
    return config.check_symbol if raw else ""


def render_table(
    rows: List[List[Any]],
    headers: Optional[List[str]] = None,
    index: bool = False,
    start_index: int = 1,
) -> str:
    """Render a list of rows as a GitHub-flavoured Markdown table.

    Args:
        rows: List of row data, where each row is a list of cell values.
        headers: Optional column header labels.
        index: If True, prepend a numeric row index. Defaults to False.
        start_index: First index value when *index* is True. Defaults to 1.

    Returns:
        Formatted Markdown table string.
    """

    options = {}
    if index:
        options["showindex"] = range(start_index, start_index + len(rows))
    if headers:
        options["headers"] = headers

    return tabulate(rows, tablefmt="github", **options)


def sanitize_cell(s: Any) -> str:
    """Collapse internal whitespace in a table cell value.

    Args:
        s: Raw cell value string.

    Returns:
        String with runs of whitespace replaced by a single space,
        or an empty string if s is falsy.
    """
    if not s:
        return ""
    s = " ".join(s.split())
    return s


def render_markdown_table(header: List[str], rows: List[List[str]]) -> str:
    """Render a plain Markdown table from a header row and data rows.

    Args:
        header: List of column header strings.
        rows: List of rows, where each row is a list of cell strings.

    Returns:
        Markdown table string with a separator row after the header.
    """
    table = []
    rows = [header, ["---"] * len(header)] + rows
    for row in rows:
        table.append(" | ".join(row))
    return "\n".join(table)


def render_maintainers(manifest: dict) -> str:
    """Render maintainer GitHub avatars as inline HTML image links.

    Args:
        manifest: Odoo manifest dict containing an optional "maintainers" list of
            GitHub usernames.

    Returns:
        HTML string of circular avatar ``<img>`` elements wrapped in ``<a>`` tags,
        or an empty string if no maintainers are listed.
    """
    maintainers = manifest.get("maintainers") or []
    return " ".join(
        [
            f"<a href='https://github.com/{x}'>"
            f"<img src='https://github.com/{x}.png' width='32' height='32' style='border-radius:50%;' alt='{x}'/>"  # noqa: E501
            "</a>"
            for x in maintainers
        ]
    )


def print_error(message: str, symbol: str = "✘") -> None:
    """Print a styled error message to the terminal in red.

    Args:
        message: Text to display.
        symbol: Prefix symbol. Defaults to "✘".
    """
    get_console().print(f"{symbol} {message}", style="red")


def print_success(message: str, symbol: str = "✔") -> None:
    """Print a styled success message to the terminal in green.

    Args:
        message: Text to display.
        symbol: Prefix symbol. Defaults to "✔".
    """
    get_console().print(f"{symbol} {message}", style="green")


def print_warning(message: str, symbol: str = "⚠") -> None:
    """Print a styled warning message to the terminal in yellow.

    Args:
        message: Text to display.
        symbol: Prefix symbol. Defaults to "⚠".
    """
    get_console().print(f"{symbol} {message}", style="yellow")


def print_rule(text: str) -> None:
    """Print a styled section banner to the terminal.

    Args:
        text: Header text to display.
    """
    console = get_console()
    console.print()
    console.print(f"── {text} ──", style="bold")


# Rich


def rule(title: str):
    console = get_console()
    console.rule(f"[brand.primary bold]{title}[/]", style="dim")


def counter_rule(title: str, value: Any) -> None:
    return rule(f"{title} ({value})")


def warning_section(messages: list[str]) -> None:
    if not messages:
        return
    console = get_console()
    console.rule(f"[yellow]Warnings ({len(messages)})[/]", style="yellow dim")
    for m in messages:
        console.print(f" {m}", style="yellow")
    console.rule(style="yellow dim")


def kv_panel(title: str, data: dict):
    console = get_console()
    content = "\n".join(f"[brand.primary]{k:<20}[/] {v}" for k, v in data.items())
    console.print(Panel(content, title=title, border_style="dim"))


def make_table(title: Optional[str], columns: list[tuple], rows: list, expand: bool = True) -> Table:
    """columns = [(label, style, justify), ...]"""

    t = Table(title=title, box=box.SIMPLE_HEAD, show_edge=False, expand=expand)
    for label, style, justify in columns:
        t.add_column(label, style=style, justify=justify)
    for row in rows:
        t.add_row(*row)
    return t


def metrics(data: dict[str, str]):
    console = get_console()
    panels = [Panel(f"[dim]{k}[/]\n[bold]{v}[/]", expand=True) for k, v in data.items()]
    console.print(Columns(panels))


# def conclude(ok: bool, message: str):
#     console = get_console()
#     icon, color = ("✓", "green") if ok else ("✗", "red")
#     console.print(f"\n[bold {color}]{icon} {message}[/]")


# def metrics_panel(title: str, data: dict[str, str], columns: int = 2):
#     console = get_console()
#     grid = Table.grid(expand=True, padding=(0, 4))
#     for _ in range(columns):
#         grid.add_column()

#     items = list(data.items())
#     for i in range(0, len(items), columns):
#         chunk = items[i : i + columns]
#         while len(chunk) < columns:
#             chunk.append(("", ""))
#         cells = [f"[dim]{k}:[/] [bold]{v}[/]" for k, v in chunk]
#         grid.add_row(*cells)

#     console.print(Panel(grid, title=title, border_style="dim"))


def metrics_grid(*panels, ratios: Optional[list[int]] = None):
    grid = Table.grid(expand=True, padding=(0, 1))
    ratios = ratios or [1] * len(panels)
    for r in ratios:
        grid.add_column(ratio=r)
    grid.add_row(*panels)
    return grid


def metrics_panel(title: str, values: list[list[str]], subtitle: Optional[str] = None):
    grid = Table.grid(expand=True)
    grid.add_column(style="dim")
    grid.add_column()
    for label, value in values:
        grid.add_row(label, colorize(value, "brand.primary"))
    return Panel(grid, title=title, subtitle=subtitle, style="dim", expand=True)


def colorize(raw: str, color: str):
    return f"[{color}]{raw}[/]"


def conclude(ok: bool, message: str):
    console = get_console()

    icon = "✓" if ok else "✗"
    style = "bold green" if ok else "bold white on dark_red"
    console.print(Panel(f"{icon}  {message}", style=style, box=box.HORIZONTALS))


def make_choices(items: set[str], preselected: set[str]) -> list[questionary.Choice]:
    return [questionary.Choice(item, checked=(item in preselected)) for item in sorted(items)]


def prompt_choices(items: set[str], preselected: set[str]):
    return questionary.checkbox(
        "Modules :",
        choices=make_choices(items, preselected),
    ).ask()


def prompt_select(message: str, choices: list[str]) -> str:
    return questionary.select(message, choices=choices).ask()


def prompt_confirm(message: str, default: bool = False) -> bool:
    return bool(questionary.confirm(message, default=default).ask())


def render_result(result: "Result") -> None:
    """Surface a Result's diagnostics to the terminal."""
    _log = logging.getLogger("oops")
    for m in result.messages:
        _log.info(m)
    warning_section(result.warnings)
    if result.errors:
        raise OopsError("\n".join(result.errors))


# ---------------------------------------------------------------------------
# Analyze command renderers
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    from oops.core.models import ClassSummary, ModuleSummary, Result, StructureSummary


def render_text(result: "Result[ModuleSummary]") -> None:
    assert result.data is not None
    summary = result.data
    console = get_console()
    m = summary.manifest
    name = m.get("name", "<unknown>")
    version = m.get("version", "")
    author = m.get("author", "")
    license_ = m.get("license", "")
    category = m.get("category", "")
    summary_text = m.get("summary", "")
    installable = m.get("installable", True)

    rule(summary.module_name)

    manifest_values = [
        ["Name", name],
        ["Version", version],
        ["Author", author],
        ["License", license_],
        ["Category", category],
        ["Installable", "yes" if installable else "no"],
    ]
    if summary_text:
        manifest_values.append(["Summary", human_readable(summary_text, width=40)])

    total_methods = sum(c.methods_total for c in summary.classes)
    total_overrides = sum(c.overrides for c in summary.classes)
    total_missing = sum(c.missing_docstrings for c in summary.classes)
    data_count = sum(n for ext in summary.structure.data.values() for n in ext.values())

    stats_values = [
        ["Models", str(len(summary.classes))],
        ["Methods", str(total_methods)],
        ["Overrides", str(total_overrides)],
        ["Missing docs", str(total_missing)],
        ["Data files", str(data_count)],
    ]

    p_manifest = metrics_panel("Manifest", manifest_values)
    p_stats = metrics_panel("Stats", stats_values)

    panels = [p_manifest, p_stats]
    if summary.loc and summary.loc.total:
        lc = summary.loc
        loc_rows = [
            ["Python", str(lc.python)],
            ["XML", str(lc.xml)],
            ["JavaScript", str(lc.javascript)],
            ["Docs", str(lc.docs)],
            ["Total", str(lc.total)],
        ]
        if summary.loc_pct:
            loc_rows.append(["% of total", f"{summary.loc_pct}%"])
        p_loc = metrics_panel("Lines of code", loc_rows)
        panels.append(p_loc)

    console.print()
    console.print(metrics_grid(*panels))
    console.print()

    depends = m.get("depends", [])
    console.print(f"Depends ({len(depends)}): {', '.join(depends) or '—'}")
    console.print()

    if summary.classes:
        counter_rule("Models", len(summary.classes))
        _render_model_table(summary.classes)
        all_overrides = [d for c in summary.classes for d in c.override_details]
        if all_overrides:
            counter_rule("Overrides", len(all_overrides))
            _render_overrides_table(all_overrides)

    _render_structure_table(summary.structure)

    if result.warnings:
        warning_section(result.warnings)


def _render_model_table(classes: list[ClassSummary]) -> None:
    console = get_console()
    columns = [
        ("Model", "brand.primary", "left"),
        ("Type", "dim", "left"),
        ("Origin", "dim", "left"),
        ("Own", "green", "right"),
        ("Inh", "green", "right"),
    ] + [(label, "green", "right") for _, label in _METHOD_COLUMNS]
    rows = []
    for c in sorted(classes, key=lambda item: item.class_name):
        label = c.model_name or ", ".join(c.inherit) or c.class_name
        origin = "new" if c.is_new_model else "inherit"
        own = str(c.fields_base if c.is_new_model else c.fields_new) if (c.fields_base or c.fields_new) else ""
        inh = str(c.fields_inherited) if c.fields_inherited else ""
        row = [label, c.model_type, origin, own, inh] + [
            str(c.methods_by_section.get(sec, "")) or "" for sec, _ in _METHOD_COLUMNS
        ]
        rows.append(row)
    console.print(make_table(title=None, columns=columns, rows=rows, expand=True))
    console.print()


def _render_overrides_table(overrides: list[dict[str, str]]) -> None:
    console = get_console()
    columns = [
        ("Model", "brand.primary", "left"),
        ("Method", "dim", "left"),
        ("Origin", "dim", "left"),
    ]
    rows = [[ov["model"], ov["method"], ov["origin_module"]] for ov in overrides]
    console.print(make_table(title=None, columns=columns, rows=rows))
    console.print()


def _render_structure_table(s: StructureSummary) -> None:
    console = get_console()
    rows = []

    for subdir, ext_counts in sorted(s.data.items()):
        for ext, count in sorted(ext_counts.items()):
            rows.append(["Data", subdir, str(count), ext, colorize("✗", "red")])

    for subdir, ext_counts in sorted(s.demo.items()):
        for ext, count in sorted(ext_counts.items()):
            rows.append(["Demo", subdir, str(count), ext, colorize("✗", "red")])

    for label, count in [
        ("wizard/", s.wizard_py),
        ("controllers/", s.controllers_py),
        ("report/", s.report_py),
    ]:
        if count:
            rows.append(["Other py", label, str(count), "py", colorize("✗", "red")])

    for ext, count in sorted(s.static_by_ext.items()):
        rows.append(["Static", f"static/src/{ext}", str(count), ext, colorize("✗", "red")])

    if not rows:
        return

    rule("Structure")
    columns = [
        ("Section", "dim", "left"),
        ("Subdir", "dim", "left"),
        ("Count", "", "right"),
        ("Ext", "dim", "left"),
        ("Analysed", "", "center"),
    ]
    console.print(make_table(title=None, columns=columns, rows=rows))
    console.print()


def render_json(result: "Result[ModuleSummary]") -> dict:
    assert result.data is not None
    summary = result.data
    not_analysed: list[str] = []
    s = summary.structure
    if s.data:
        not_analysed.append("data")
    if s.demo:
        not_analysed.append("demo")
    if s.controllers_py:
        not_analysed.append("controllers/")
    if s.wizard_py:
        not_analysed.append("wizard/")
    if s.report_py:
        not_analysed.append("report/")
    if s.static_by_ext:
        not_analysed.append("static/")

    loc = summary.loc
    loc_block = (
        {
            "python": loc.python,
            "xml": loc.xml,
            "javascript": loc.javascript,
            "docs": loc.docs,
            "total": loc.total,
            "pct": summary.loc_pct,
        }
        if loc is not None
        else {"python": 0, "xml": 0, "javascript": 0, "docs": 0, "total": 0, "pct": 0.0}
    )

    return {
        "module": summary.module_name,
        "manifest": {
            "name": summary.manifest.get("name", "<unknown>"),
            "version": summary.manifest.get("version", ""),
            "author": summary.manifest.get("author", ""),
            "license": summary.manifest.get("license", ""),
            "category": summary.manifest.get("category", ""),
            "installable": summary.manifest.get("installable", True),
            "depends": summary.manifest.get("depends", []),
            "summary": summary.manifest.get("summary", ""),
        },
        "models": [
            {
                "class_name": c.class_name,
                "model_name": c.model_name,
                "is_new_model": c.is_new_model,
                "inherit": c.inherit,
                "fields": {
                    "total": c.fields_total,
                    "base": c.fields_base,
                    "new": c.fields_new,
                    "inherited": c.fields_inherited,
                    "by_type": c.fields_by_type,
                },
                "methods": {
                    "total": c.methods_total,
                    "by_section": c.methods_by_section,
                    "overrides": c.overrides,
                    "override_details": c.override_details,
                    "missing_docstrings": c.missing_docstrings,
                },
            }
            for c in summary.classes
        ],
        "structure": {
            "data": s.data,
            "demo": s.demo,
            "controllers_py": s.controllers_py,
            "wizard_py": s.wizard_py,
            "report_py": s.report_py,
            "static_by_ext": s.static_by_ext,
        },
        "loc": loc_block,
        "not_analysed": not_analysed,
        "warnings": result.warnings,
    }
