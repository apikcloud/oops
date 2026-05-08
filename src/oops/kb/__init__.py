# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: __init__.py — oops/kb/__init__.py

"""Knowledge Base package: scanner, store, resolver, and shared rich console."""

import logging

from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_kb_logging(verbose: bool) -> None:
    """Configure root logging with a Rich handler for KB commands."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, markup=True)],
    )
