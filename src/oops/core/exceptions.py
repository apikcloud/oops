# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: exceptions.py — oops/core/exceptions.py

# Exit and exception handling patterns.
#
# QUICK REFERENCE
# ===============
#
# | Situation                        | Location         | Pattern                        | Exit code |
# |----------------------------------|------------------|--------------------------------|-----------|
# | Normal end                       | command          | implicit return                | 0         |
# | Early exit (clean)               | command          | explicit return                | 0         |
# | Early exit (clean)               | sub-function     | raise EarlyExit()              | 0         |
# | Generic business error           | anywhere         | raise OopsError(msg)           | 1         |
# | Specialized business error       | anywhere         | raise ConfigError(msg)         | 1+        |
# | User cancellation                | anywhere         | raise AppAbort()               | 1         |
# | Bad CLI usage (shows help)       | anywhere         | raise click.UsageError(msg)    | 2         |
# | Unexpected Python exception      | —                | auto-wrapped into OopsError    | 1         |
#
# WHY EarlyExit AND NOT ctx.exit(0) OR sys.exit(0)?
# ==================================================
#
#     ctx.exit(0) and sys.exit(0) only work from code that has access to the
#     current context, and they bypass any context managers or cleanup logic
#     still on the call stack.  Raising EarlyExit() instead:
#
#       - works from any sub-function at any depth (no ctx needed)
#       - unwinds the stack normally, so `with` blocks and __exit__ hooks run
#       - is intercepted once and only once in OopsCommand.invoke()
#       - plays nicely with CliRunner in tests (no real SystemExit is raised)
#
# RULES FOR DEVELOPERS
# ====================
#
# DO
#     raise EarlyExit()          from any sub-function to exit cleanly with code 0
#     raise OopsError(msg)       for any business-level error
#     raise AppAbort()           when the user explicitly cancels an action
#     raise click.UsageError()   for bad CLI usage (wrong args, forbidden combos)
#     return                     directly inside a command for early clean exit
#
# DO NOT
#     sys.exit()    — bypasses Click lifecycle and breaks CliRunner in tests
#     ctx.exit()    — same issue; reserved for the OopsCommand handler only
#     raise any raw Python exception — wrap it as OopsError instead

import click
from rich.console import Console

# Console helpers


def get_error_console() -> Console:
    """Return a stderr-bound Rich Console (see ``get_console``)."""
    return Console(stderr=True, highlight=False, soft_wrap=False)


# Warnings


class DeprecatedRegistryWarning(UserWarning):
    """Warning for deprecated Docker registries."""


class UnusualRegistryWarning(UserWarning):
    """Warning for unusual Docker registries."""


# Exceptions


class ConfigurationError(Exception):
    """Raised when required configuration values are missing."""


class NoManifestFound(Exception):
    """Raised when no manifest file is found in an addon."""



class MissingMandatoryFiles(Exception):
    """Raised when mandatory files are missing."""

    message = "Mandatory files are missing: {files}"

    def __init__(self, files):
        self.files = files
        self.message = self.message.format(files=", ".join(files))
        super().__init__(self.message)


class MissingRecommendedFiles(MissingMandatoryFiles):
    """Raised when recommended files are missing."""

    message = "Recommended files are missing: {files}"


class OopsError(click.ClickException):
    """Fatal error raised by oops commands.

    Renders as ``✘ <message>`` in red on stderr (matching ``print_error``'s
    visual style) and exits with code 1 via Click's standard exception flow,
    so ``OopsCommand`` telemetry records it as ``Exit(1)``.

    Use this for runtime errors that should terminate the command. For bad
    user input prefer ``click.UsageError``; for explicit non-error exits
    prefer ``click.exceptions.Exit(N)``.
    """

    def show(self, file=None) -> None:  # noqa: ARG002 - signature mirrors click.ClickException
        get_error_console().print(f"✘ {self.format_message()}", style="red")


class EarlyExit(Exception):
    """
    Signals a clean, intentional early exit with code 0.

    Raise this from any function at any call depth when the command should
    stop immediately without error — for example, when a resource is already
    up-to-date and there is nothing to do.

    Never catch this in commands or sub-functions: let it propagate up to
    AppGroup.invoke(), which intercepts it and calls ctx.exit(0).

    Example::

        def check_already_deployed(config: dict) -> None:
            if config.get("already_deployed"):
                click.echo("Nothing to do.")
                raise EarlyExit()
    """


class ConfigError(OopsError):
    """
    Raised when configuration is missing, malformed, or incomplete.

    Example::

        raise ConfigError("Key 'database.url' not found in config.yml")
    """

    exit_code = 1


class APIError(OopsError):
    """
    Raised when a remote API call fails.

    Example::

        raise APIError(f"Deploy endpoint returned HTTP {response.status_code}")
    """

    exit_code = 2


class NotFoundError(OopsError):
    """
    Raised when a required resource cannot be found.

    Example::

        raise NotFoundError(f"Environment '{env}' does not exist")
    """

    exit_code = 3


class AppAbort(click.Abort):
    """
    Signals an explicit, intentional user cancellation.

    Distinct from a raw KeyboardInterrupt (Ctrl+C), which Click already
    converts to click.Abort automatically. Use AppAbort when the user
    declines a confirmation prompt or triggers a cancel action in your code.

    Click prints "Aborted!" to stderr and exits with code 1.

    Example::

        if not click.confirm(f"Deploy to '{env}'?"):
            raise AppAbort()
    """
