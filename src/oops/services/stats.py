# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: stats.py — oops/services/stats.py

"""Local usage-event collection and periodic flush to a remote endpoint.

Events are appended as JSON lines to ``~/.local/share/oops/stats.jsonl``.
A flush is attempted at CLI startup when the last successful flush was more
than 7 days ago.  All I/O errors are silently swallowed so the feature never
blocks normal CLI operation.
"""

import datetime
import getpass
import json
import secrets

import requests
from oops.core.paths import stats_file, stats_flush_marker

_FLUSH_INTERVAL_DAYS = 7


# ---------------------------------------------------------------------------
# Event collection
# ---------------------------------------------------------------------------


def append_event(cmd: str, ms: float, error: "str | None") -> None:
    """Append one usage event as a JSON line to the stats file.

    Silently does nothing if stats are disabled or any I/O error occurs.

    Args:
        cmd: Command identifier, e.g. ``"addons download"``.
        ms: Elapsed time in milliseconds.
        error: Exception class name if the command raised, otherwise ``None``.
    """
    try:
        from oops.core.config import config  # local import to avoid circular deps

        if not config.stats.enabled:
            return

        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        event = {
            "ts": ts,
            "cmd": cmd,
            "ms": ms,
            "user": _get_user(),
            "error": error,
        }
        path = stats_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _get_user() -> str:
    """Return the current Unix username, falling back to ``"unknown"``.

    Returns:
        Username string, or ``"unknown"`` if resolution fails.
    """
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "unknown"


# ---------------------------------------------------------------------------
# Flush
# ---------------------------------------------------------------------------


def maybe_flush() -> None:
    """Flush pending events if the last flush was more than 7 days ago.

    Silently does nothing when stats are disabled, the flush is not due yet,
    or any error occurs.
    """
    try:
        from oops.core.config import config  # local import to avoid circular deps

        if not config.stats.enabled:
            return
        if not config.stats.endpoint:
            return
        if not _flush_due():
            return
        flush_stats()
    except Exception:  # noqa: BLE001
        pass


def _flush_due() -> bool:
    """Return ``True`` if a flush has not been performed within the interval.

    Returns:
        ``True`` when the marker file is absent, unreadable, or older than
        ``_FLUSH_INTERVAL_DAYS`` days; ``False`` otherwise.
    """
    marker = stats_flush_marker()
    if not marker.exists():
        return True
    try:
        last = datetime.datetime.fromtimestamp(marker.stat().st_mtime, tz=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - last).days >= _FLUSH_INTERVAL_DAYS
    except Exception:  # noqa: BLE001
        return True


def flush_stats() -> None:
    """Read all pending events, POST them to the configured endpoint, then truncate.

    Args are read from ``config.stats``.  Raises on HTTP or I/O errors so that
    :func:`maybe_flush` can catch and swallow them silently.
    """
    from oops.core.config import config  # local import to avoid circular deps

    path = stats_file()
    if not path.exists():
        _touch_marker()
        return

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        _touch_marker()
        return

    endpoint = config.stats.endpoint
    if not endpoint:
        return

    events = [json.loads(line) for line in raw.splitlines() if line.strip()]

    requests.post(
        endpoint,
        json={"events": events},
        headers={"X-Oops-Token": secrets.token_hex(16)},
        timeout=5,
    )

    path.write_text("", encoding="utf-8")
    _touch_marker()


def _touch_marker() -> None:
    """Update the flush marker file to the current timestamp, creating it if absent."""
    marker = stats_flush_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
