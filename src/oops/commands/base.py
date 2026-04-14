# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: base.py — oops/commands/base.py

import time
from typing import Any

import click
from oops.core.config import config
from oops.core.exceptions import ConfigurationError
from oops.services.stats import append_event, maybe_flush


def _cmd_name(ctx: click.Context) -> str:
    """Return the group+command identifier, e.g. ``"project check"``.

    Derives the name from the callback's module path
    (``oops.commands.project.check``) so the result is consistent regardless
    of whether the command was invoked via ``oops project check`` or the
    abbreviated entry point ``oops-pro-check``.
    """
    cb = ctx.command.callback
    if cb is not None:
        parts = getattr(cb, "__module__", "").split(".")
        # "oops.commands.project.check" → "project check"
        if len(parts) >= 4 and parts[:2] == ["oops", "commands"]:
            return " ".join(parts[2:])
    # Fallback: walk the context parent chain.
    parts = []
    c = ctx
    while c.parent is not None:
        parts.append(c.info_name or "")
        c = c.parent
    parts.reverse()
    return " ".join(p for p in parts if p)


class OopsCommand(click.Command):
    """Base Click command that validates config and tracks usage."""

    def invoke(self, ctx: click.Context) -> Any:
        # Trigger lazy config load before the callback runs.
        # --help exits during make_context() and never reaches this point.
        try:
            config.default_timeout  # noqa: B018
        except ConfigurationError as e:
            raise click.UsageError(str(e)) from None

        maybe_flush()

        cmd = _cmd_name(ctx)
        t0 = time.monotonic()
        error = None
        try:
            return super().invoke(ctx)
        except click.exceptions.Exit as exc:
            # Exit(0) is a voluntary clean exit — not an error.
            if exc.exit_code != 0:
                error = f"Exit({exc.exit_code})"
            raise
        except click.Abort:
            # User-initiated abort (Ctrl-C / raise Abort()) — not an error.
            raise
        except SystemExit as exc:
            # Direct sys.exit() calls — record non-zero codes.
            code = exc.code
            if isinstance(code, int) and code != 0:
                error = f"Exit({code})"
            raise
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            ms = round((time.monotonic() - t0) * 1000, 1)
            try:
                append_event(cmd, ms, error)
            except Exception:  # noqa: BLE001
                pass


def command(*args: Any, **kwargs: Any):
    """Drop-in replacement for @click.command that uses OopsCommand by default."""
    kwargs.setdefault("cls", OopsCommand)
    return click.command(*args, **kwargs)
