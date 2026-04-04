# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: helpers.py — oops/utils/helpers.py

from datetime import date

from oops.utils.compat import PY38, Any, List


def removesuffix(raw, suffix) -> str:
    """Remove a suffix from a string if present, compatible with Python < 3.9.

    Args:
        raw: Input string to process.
        suffix: Suffix to strip if present.

    Returns:
        String with the suffix removed, or the original string if not present.
    """

    # str.removesuffix added in 3.8
    if PY38:
        return raw[: len(raw) - len(suffix)] if raw[-len(suffix) :] == suffix else raw
    return raw.removesuffix(suffix)


def clean_string(raw: Any) -> str:
    """Convert a value to a stripped string, returning an empty string for falsy input.

    Args:
        raw: Value to convert and clean.

    Returns:
        Stripped string, or an empty string if raw is falsy.
    """

    return str(raw).strip().rstrip() if raw else ""


def str_to_list(raw: str, sep=",") -> list:
    """Split a separated string into a list of cleaned, non-empty items.

    Args:
        raw: Input string to split.
        sep: Separator character or string. Defaults to ",".

    Returns:
        List of stripped, non-empty strings.
    """

    if not raw:
        return []
    return list(filter(bool, (clean_string(item) for item in raw.split(sep))))


def deep_visit(obj, prefix=""):
    """Yield flattened (path, value) pairs by recursively walking a nested structure.

    Dict keys become dot-separated segments; list indices become ``[n]`` segments.
    Example: ``assets.web.assets_backend[0]`` → ``"/module/static/..."``

    Args:
        obj: Nested dict, list, tuple, or scalar to walk.
        prefix: Accumulated path prefix for the current node. Defaults to "".

    Yields:
        Tuple of (dotted_path_string, leaf_value) for each scalar encountered.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            yield from deep_visit(v, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from deep_visit(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def filter_and_clean(items: List[str]) -> set:
    """Filter comment lines and clean inline comments from a list of strings.

    Strips full-line comments (starting with ``#``), blank lines, and inline
    comments (everything after ``#`` on a line).

    Args:
        items: Lines of text to process.

    Returns:
        Set of cleaned, non-empty, non-comment strings.
    """

    def clean(item):
        if "#" not in item:
            return item.strip()

        return item.split("#")[0].strip()

    items = list(filter(lambda item: item and not item.startswith("#"), items))

    return set(map(clean, items))


def date_from_string(raw: str) -> date:
    """Convert an 8-character YYYYMMDD string into a date object.

    Args:
        raw: Date string in YYYYMMDD format (exactly 8 characters).

    Returns:
        Corresponding date object.

    Raises:
        ValueError: If raw is not exactly 8 characters long.
    """

    if len(raw) != 8:  # noqa: PLR2004
        raise ValueError("The string does not have the correct length to be converted to a date.")

    y, m, d = int(raw[0:4]), int(raw[4:6]), int(raw[6:8])
    return date(y, m, d)
