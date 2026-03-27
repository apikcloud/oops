# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: render.py — oops/utils/render.py

import textwrap
from datetime import datetime

import click
from oops.core.config import config
from oops.utils.compat import Any, List, Optional
from tabulate import tabulate


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
    click.echo(click.style(f"{symbol} {message}", fg="red"))


def print_success(message: str, symbol: str = "✔") -> None:
    """Print a styled success message to the terminal in green.

    Args:
        message: Text to display.
        symbol: Prefix symbol. Defaults to "✔".
    """
    click.echo(click.style(f"{symbol} {message}", fg="green"))


def print_warning(message: str, symbol: str = "⚠") -> None:
    """Print a styled warning message to the terminal in yellow.

    Args:
        message: Text to display.
        symbol: Prefix symbol. Defaults to "⚠".
    """
    click.echo(click.style(f"{symbol} {message}", fg="yellow"))
