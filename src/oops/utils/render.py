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


def format_days(total_days: int) -> str:
    """Format a total number of days into a human-readable duration string.

    Breaks the duration down into years (365 days), months (30 days), and
    remaining days, omitting any leading zero components.

    Args:
        total_days: Total number of days to format. Must be >= 0.

    Returns:
        A human-readable string such as "2 year(s), 3 month(s), 5 days",
        "4 month(s), 2 days", or "18 days".

    Raises:
        ValueError: If total_days is negative.
    """
    if total_days < 0:
        raise ValueError(f"total_days must be >= 0, got {total_days}")

    DAYS_IN_YEAR = 365
    DAYS_IN_MONTH = 30

    years, remaining = divmod(total_days, DAYS_IN_YEAR)
    months, days = divmod(remaining, DAYS_IN_MONTH)

    parts = []
    if years:
        parts.append(f"{years} year{'s' if years > 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months > 1 else ''}")
    parts.append(f"{days} day{'s' if days != 1 else ''}")

    return ", ".join(parts)


def approximate_duration(total_days: int) -> str:
    """Render an approximate duration as a human-readable string.

    Args:
        total_days: Total number of days. Must be >= 0.

    Returns:
        A natural-language string such as "< 1 month", "2 months", "1 and a half years".

    Raises:
        ValueError: If total_days is negative.
    """
    if total_days < 0:
        raise ValueError(f"total_days must be >= 0, got {total_days}")

    WEEK = 7
    MONTH = 30
    YEAR = 365

    weeks = total_days / WEEK
    months = total_days / MONTH
    years = total_days / YEAR

    # --- Days (0–6) ---
    if total_days == 0:
        return "0 days"
    if total_days == 1:
        return "1 day"
    if total_days < WEEK:
        return f"{total_days} days"

    # --- Weeks / approaching one month (7–29 days) ---
    # Round to nearest week; if we're close to a full month say "~1 month"
    if total_days < MONTH:
        return "~1 month" if round(weeks) >= 4 else "< 1 month"

    # --- Months (30–364 days) ---
    if total_days < YEAR:
        m = round(months)
        if m < 2:
            return "~1 month"
        # Close to a full year: avoid "11 months", prefer "< 1 year"
        if m >= 11:
            return "< 1 year"
        return f"{m} months"

    # --- Years (365+ days) ---
    # 1.0–1.25 years → plain "1 year"
    if years < 1.25:
        return "1 year"
    # 1.25–1.75 years → "1 and a half years"
    if years < 1.75:
        return "1 and a half years"

    y = round(years)
    remainder_months = round((years - round(years)) * 12)

    # Close to the next full year (≥ 10 leftover months): prefer "< N years"
    if remainder_months >= 10:
        return f"< {y + 1} years"
    # More than half a year left over: "N and a half years"
    if remainder_months >= 6:
        return f"{y} and a half years"
    # Otherwise round to the nearest full year
    return f"{y} years" if y > 1 else "1 year"


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
    # console.rule(style="yellow dim")


def error_section(messages: list[str]) -> None:
    """Print errors to stderr in red. No-op if empty."""
    console = get_error_console()

    console.rule(f"[red]Errors ({len(messages)})[/]", style="red dim")
    for m in messages:
        console.print(f" {m}", style="red")
    # console.rule(style="red dim")


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
    console = get_console() if ok else get_error_console()

    icon = "✓" if ok else "✗"
    style = "bold green" if ok else "bold dark_red"

    console.print(Panel(f"{icon}  {message}", style=style))


def print_result(ok: bool, message: str):
    console = get_console() if ok else get_error_console()

    icon = "✓" if ok else "✗"
    style = "bold green" if ok else "bold dark_red"

    console.print(f"{icon}  {message}", style=style)


def make_choices(items: set[str], preselected: set[str]) -> list[questionary.Choice]:
    return [questionary.Choice(item, checked=(item in preselected)) for item in sorted(items)]


def prompt_choices(message: str, items: set[str], preselected: set[str]):
    return questionary.checkbox(
        message,
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


def render_panel(title: str, content: str):
    console = get_error_console()
    console.print(Panel(content, title=title, border_style="dim"))


def render_healder(ctx) -> None:

    if ctx.parent is not None:
        return

    import time

    from oops.io.file import decode_payload

    console = get_error_console()
    console.clear()

    console.print(decode_payload(0))
    time.sleep(3)
    console.clear()


def render_footer(ctx) -> None:

    if ctx.parent is not None:
        return

    import time
    from random import randrange

    from oops.io.file import decode_payload

    content = decode_payload(1)
    console = get_error_console()

    height = console.size.height

    try:
        time.sleep(3)
        console.clear()
        for line, _ in zip(content.splitlines(), range(0, height - 2)):
            console.print(line, highlight=False, style="brand.primary")
            time.sleep(randrange(2, 15) / 100)

    except KeyboardInterrupt:
        pass


def clear_screen() -> None:
    console = get_console()
    console.clear()
