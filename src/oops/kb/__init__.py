# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: __init__.py — oops/kb/__init__.py

"""Knowledge Base package: scanner, store, resolver, and shared logging setup."""

import logging


def setup_kb_logging(verbose: bool) -> None:
    """Configure root logging for KB commands.

    Args:
        verbose: If True, set level to DEBUG; otherwise INFO.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )
