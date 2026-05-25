# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: render.py — oops/utils/render.py

from __future__ import annotations

import textwrap
from datetime import date, datetime

import questionary
from oops.core.compat import Any, List, Optional
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.logger import log
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.style import Style
from rich.table import Table
from rich.theme import Theme
from tabulate import tabulate

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


def format_date(dt: date) -> str:
    """Format a date as a string using the configured date format.

    Args:
        dt: Date object to format.

    Returns:
        Formatted date string.
    """

    return dt.strftime(config.date_format)


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


def experimental_warning() -> None:
    print_warning("This command is experimental and may change without notice between releases.")


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


def ask(message: str) -> str:
    return Prompt.ask(message)


def render_result(result) -> None:
    """Surface a Result's diagnostics to the terminal."""

    for m in result.messages:
        log.info(m)
    warning_section(result.warnings)
    if result.errors:
        raise OopsError("\n".join(result.errors))
