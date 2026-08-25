# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: __init__.py — oops_engine/__init__.py

"""Source-analysis engine: scanner, store, resolver. No dependency on oops.core.config,
oops.services, oops.commands, or Click."""

from oops_engine.resolver import InheritanceResolver

__all__ = ["InheritanceResolver"]

