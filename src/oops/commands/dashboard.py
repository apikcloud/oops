# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: dashboard.py — src/oops/commands/dashboard.py

"""
oops — pywebview dashboard

Synthesis view for oops projects: runs oops commands via subprocess
(``python -m oops <cmd> --format json``) and renders the JSON payloads
in the single-file SPA.
"""

from __future__ import annotations

import click
from oops.commands.base import command
from oops.core.paths import UI
from oops.dashboard.api import Api

GUI = "qt"


@command(name="dashboard", help="Launch the oops dashboard (desktop GUI).")
@click.option("--debug", is_flag=True, default=False, hidden=True, help="Open devtools.")
def main(debug: bool) -> None:
    try:
        import webview  # noqa: PLC0415
    except ImportError as error:
        from oops.core.exceptions import OopsError

        raise OopsError(
            "pywebview is required for `oops dashboard`. Install with: pip install 'oops\\[dashboard]'"
        ) from error

    api = Api()
    webview.create_window(
        "oops",
        url=str(UI / "index.html"),
        js_api=api,
        width=1440,
        height=900,
        min_size=(900, 600),
        resizable=True,
        confirm_close=False,
    )
    # js_api calls run off the GUI thread, so a blocking command won't freeze
    # the window — the JS side just awaits.
    webview.start(debug=debug, gui=GUI)
