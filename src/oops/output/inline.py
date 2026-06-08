# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: inline.py — src/oops/output/inline.py

"""Assemble a single self-contained HTML report from the shared UI bundle.

Takes the UI shell (output/ui/index.html), inlines its CSS and the built JS
bundle (output/ui/dist/app.bundle.js), and freezes the payload as
``window.OOPS``. The result has zero external dependencies — openable over
file:// and shareable as one file. This replaces the per-command templates.

The JS bundle is a *build product*: produced by esbuild in the release CI
(`npm run build` in output/ui), committed and shipped as package data.
"""

from __future__ import annotations

import re

from oops.core.paths import UI
from oops.output.serializers import to_json_string

_CSS_LINK = re.compile(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"[^>]*>')
_BUNDLE = re.compile(r'<script[^>]*src="(\./dist/[^"]+)"[^>]*></script>')
_DATA = re.compile(r'<script[^>]*src="\./data\.js"[^>]*></script>')


def _read(rel: str) -> str:
    return (UI / rel.lstrip("./")).read_text(encoding="utf-8")


def _freeze(payload: dict) -> str:
    # Inline JSON in an HTML <script> context: neutralise "</script>" and friends.
    return to_json_string(payload).replace("<", "\\u003c")


def build_report(payload: dict) -> str:
    """Return one self-contained HTML document for `payload`."""
    html = _read("index.html")
    html = _CSS_LINK.sub(lambda m: f"<style>\n{_read(m.group(1))}\n</style>", html)
    # freeze the payload where data.js would have loaded it
    html = _DATA.sub(lambda _: f"<script>window.OOPS = {_freeze(payload)};</script>", html)
    # inline the JS bundle last (so the payload is defined before it runs)
    html = _BUNDLE.sub(lambda m: f"<script>\n{_read(m.group(1))}\n</script>", html)
    return html
