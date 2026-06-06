# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: dashboard.py — src/oops/commands/dashboard.py

"""
oops — pywebview PoC

Goal: a project *synthesis* dashboard that can launch a few oops commands.
NOT a port of `oops serve` (the per-module reference SPA).
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.paths import WEB

# --- Wire these to the real oops entry points -------------------------------
# from oops.commands.addons import list_addons, analyze_modules
#
# Each should return an object with `.to_machine()` giving the dict shape the
# SPA renders (the addons.json / analyze.json payloads).
# ---------------------------------------------------------------------------

HERE = Path(__file__).parent
SAMPLES = HERE / "samples"  # dev fallback payloads (addons.json, analyze.json)


def _fallback(name: str) -> dict:
    """Dev fallback so the window runs before the real logic is wired."""
    p = SAMPLES / name
    if p.exists():
        return json.loads(p.read_text())
    return {"metadata": {"command": "error"}, "error": f"no sample {name} and oops not wired"}


class Api:
    def __init__(self) -> None:
        self._project_path: str | None = None

    # --- project synthesis: the `addons list` payload ----------------------
    def scan_project(self, path: str | None = None) -> dict:
        path = path or self._project_path
        # result = list_addons(path); return result.to_machine()
        return _fallback("addons.json")

    # --- deep dive on one module: the `addons analyze` payload --------------
    def analyze_module(self) -> dict:
        target = self._pick_folder("Select a module to analyze")
        if not target:
            return {"metadata": {"command": "cancelled"}}
        # result = analyze_modules([target]); return result.to_machine()
        return _fallback("analyze.json")

    # --- pick the project root (native folder dialog) ----------------------
    def pick_project(self) -> str | None:
        chosen = self._pick_folder("Select the project root")
        if chosen:
            self._project_path = chosen
            return self._project_path
        return None

    def project_path(self) -> str | None:
        return self._project_path

    # --- helpers -----------------------------------------------------------
    def _pick_folder(self, title: str) -> str | None:
        import webview  # noqa: PLC0415

        win = webview.windows[0]
        res = win.create_file_dialog(webview.FileDialog.FOLDER, allow_multiple=False)
        # create_file_dialog returns a tuple/list of paths or None
        if not res:
            return None
        return res[0] if isinstance(res, (list, tuple)) else res


@command(name="dashboard", help="Launch the oops project synthesis dashboard (desktop GUI).")
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
        url=str(WEB / "index.html"),
        js_api=api,
        width=1200,
        height=820,
        min_size=(900, 600),
    )
    # js_api calls run off the GUI thread, so a blocking command won't freeze
    # the window — the JS side just awaits.
    webview.start(debug=debug)
