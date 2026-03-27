# oops/render.py
"""
Rendering utilities for tables and formatted output.
"""

import textwrap
from datetime import datetime

from tabulate import tabulate

from oops.core.config import config
from oops.utils.compat import Any, List, Optional


def format_datetime(dt: datetime) -> str:
    """
    Format a datetime object as a string using the module's config.datetime_format.
    """

    return dt.strftime(config.datetime_format)


def human_readable(raw: Any, sep: str = ", ", width: Optional[int] = None) -> str:
    """Convert a value to a human-readable string."""

    if isinstance(raw, bool):
        return "yes" if raw else "no"
    if isinstance(raw, (list, tuple, set)):
        return sep.join(map(str, raw))

    if width:
        return textwrap.shorten(raw, width=width, placeholder="...")

    return str(raw)


def render_boolean(raw: bool) -> str:
    """
    Render a check mark if the terminal supports UTF-8, otherwise an 'OK'.
    """
    return config.check_symbol if raw else ""


def render_table(
    rows: List[List[Any]], headers: Optional[List[str]] = None, index: bool = False
) -> str:
    """
    Render a table using the tabulate library.
    """

    options = {}
    if index:
        options["showindex"] = True
    if headers:
        options["headers"] = headers

    return tabulate(rows, tablefmt="github", **options)


def sanitize_cell(s):
    if not s:
        return ""
    s = " ".join(s.split())
    return s


def render_markdown_table(header, rows):
    table = []
    rows = [header, ["---"] * len(header)] + rows
    for row in rows:
        table.append(" | ".join(row))
    return "\n".join(table)


def render_maintainers(manifest):
    maintainers = manifest.get("maintainers") or []
    return " ".join(
        [
            f"<a href='https://github.com/{x}'>"
            f"<img src='https://github.com/{x}.png' width='32' height='32' style='border-radius:50%;' alt='{x}'/>"  # noqa: E501
            "</a>"
            for x in maintainers
        ]
    )
