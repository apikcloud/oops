# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: base.py — oops/commands/base.py

from typing import Any

import click
from oops.core.config import config
from oops.core.exceptions import ConfigurationError


class OopsCommand(click.Command):
    """Base Click command that validates config before invoking the callback."""

    def invoke(self, ctx: click.Context) -> Any:
        # Trigger lazy config load before the callback runs.
        # --help exits during make_context() and never reaches this point.
        try:
            config.default_timeout  # noqa: B018
        except ConfigurationError as e:
            raise click.UsageError(str(e)) from None
        return super().invoke(ctx)


def command(*args: Any, **kwargs: Any):
    """Drop-in replacement for @click.command that uses OopsCommand by default."""
    kwargs.setdefault("cls", OopsCommand)
    return click.command(*args, **kwargs)
