# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: __init__.py — src/oops/output/markdown/__init__.py

"""Rendering internals for the Markdown documentation site.

Kept out of the already-large ``output/formatters.py``: ``cards`` formats
descriptor-driven stat blocks, ``pages`` builds the index / module / model
Markdown pages, and ``mermaid`` (Phase 4) emits the audit graphs. The
``MarkdownSiteFormatter`` in ``formatters.py`` calls these builders.
"""
