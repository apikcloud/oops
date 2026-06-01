# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: logger.py — src/oops/core/logger.py

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Optional

from oops.core.exceptions import get_error_console
from rich.live import Live
from rich.spinner import Spinner

ProgressCallback = Callable[[str], None]

_progress_callback: ContextVar[Optional[ProgressCallback]] = ContextVar("progress_callback", default=None)


class ProgressHandler(logging.Handler):
    """Logging handler that routes records to the active Rich Live progress display."""

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a log record to the current progress callback, if one is active."""
        callback = _progress_callback.get()
        if callback is not None:
            callback(self.format(record))
        # sinon, on laisse les autres handlers faire leur travail


@contextmanager
def live_progress(message: str, spinner: str = "dots", enabled: bool = True):
    """Context manager that shows a Rich spinner while a block runs.

    Log messages emitted via ``log`` inside the block update the spinner text
    instead of printing to the console.

    Args:
        message: Initial spinner label.
        spinner: Rich spinner name (default ``"dots"``).
        enabled: When False the context manager is a no-op (useful in CI/tests).

    Yields:
        The active ``rich.live.Live`` instance, or None when disabled.
    """
    if not enabled:
        yield None
        return

    with Live(Spinner(spinner, text=message), console=get_error_console(), refresh_per_second=10) as live:

        def update_status(_message: str):
            live.update(Spinner(spinner, text=_message))

        token = _progress_callback.set(update_status)
        # log.propagate = False
        try:
            yield live
        finally:
            # log.propagate = True
            _progress_callback.reset(token)


# setup
log = logging.getLogger("oops")
log.setLevel(logging.INFO)
log.propagate = False
log.addHandler(ProgressHandler())
