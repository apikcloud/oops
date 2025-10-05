# osh/render.py
"""
Rendering utilities for tables and formatted output.
"""

import textwrap
from datetime import datetime

from tabulate import tabulate

from osh.compat import Any, List, Optional
from osh.settings import CHECK_SYMBOL, DATETIME_FORMAT


def format_datetime(dt: datetime) -> str:
    """
    Format a datetime object as a string using the module's DATETIME_FORMAT.
    """

    return dt.strftime(DATETIME_FORMAT)


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
    return "X" if raw else ""
    return CHECK_SYMBOL if raw else ""


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
