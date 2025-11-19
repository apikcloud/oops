from datetime import date

from oops.utils.compat import PY38, Any, List


def removesuffix(raw, suffix) -> str:
    """Remove suffix from string if present (Python < 3.9 compatible)."""

    # str.removesuffix added in 3.8
    if PY38:
        return raw[: len(raw) - len(suffix)] if raw[-len(suffix) :] == suffix else raw
    return raw.removesuffix(suffix)


def clean_string(raw: Any) -> str:
    """Convert a value to a cleaned string (stripped, no trailing spaces)."""

    return str(raw).strip().rstrip() if raw else ""


def str_to_list(raw: str, sep=",") -> list:
    """Convert a separated string to a list of cleaned items."""

    if not raw:
        return []
    return list(filter(bool, (clean_string(item) for item in raw.split(sep))))


def deep_visit(obj, prefix=""):
    """
    Yield flattened (path, value) pairs for recursive inspection.
    Example: 'assets.web.assets_backend[0]' -> '/module/static/...'
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
    """Filter and clean text file"""

    def clean(item):
        if "#" not in item:
            return item.strip()

        return item.split("#")[0].strip()

    items = list(filter(lambda item: item and not item.startswith("#"), items))

    return set(map(clean, items))


def date_from_string(raw: str) -> date:
    """
    Convert an 8-character string in YYYYMMDD format into a datetime.date object.
    """

    if len(raw) != 8:  # noqa: PLR2004
        raise ValueError("The string does not have the correct length to be converted to a date.")

    y, m, d = int(raw[0:4]), int(raw[4:6]), int(raw[6:8])
    return date(y, m, d)
