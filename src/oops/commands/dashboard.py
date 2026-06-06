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

import json
import subprocess
import sys
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.paths import WEB


def _run_oops(args: list[str], cwd: str, timeout: int = 180) -> dict:
    """Run ``oops <args> --format json`` in *cwd* and return the parsed payload.

    Check commands exit non-zero when a check fails but still print the JSON
    payload to stdout, so the payload is parsed regardless of the return code.
    A non-JSON stdout (a real crash) surfaces stderr as an error payload that
    the SPA renders via its "error" view.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "oops", *args, "--format", "json"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        msg = proc.stderr.strip() or f"oops {' '.join(args)} failed (exit {proc.returncode})"
        return {"metadata": {"command": "error"}, "error": msg}


def _current_project() -> "str | None":
    """Resolve the git repo root for the launch cwd, or None if not in a repo."""
    try:
        from oops.services.git import require_repository  # noqa: PLC0415

        _, repo_path = require_repository()
        return str(repo_path)
    except Exception:
        return None


class Api:
    def __init__(self) -> None:
        self._current = _current_project()
        self._project_path: "str | None" = self._current

    # --- project selector --------------------------------------------------
    def list_projects(self) -> dict:
        from oops.core.config import config  # noqa: PLC0415
        from oops.services.project import find_projects  # noqa: PLC0415

        projects: list[dict] = []
        wd = config.working_dir
        if wd:
            for p in find_projects(Path(wd).expanduser()):
                projects.append({"path": str(p), "name": p.name})
        # Always expose the current project even if outside working_dir.
        if self._current and not any(pr["path"] == self._current for pr in projects):
            projects.insert(0, {"path": self._current, "name": Path(self._current).name})
        return {"projects": projects, "current": self._current, "working_dir": wd}

    def select_project(self, path: str) -> str:
        self._project_path = path
        return path

    # --- payloads (subprocess → machine dict) ------------------------------
    def scan_project(self, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        return _run_oops(["addons", "list"], cwd=path)

    def analyze_module(self, module_path: str, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        return _run_oops(["addons", "analyze", module_path], cwd=path)

    def check_project(self, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        return _run_oops(["project", "check"], cwd=path)

    def check_requirements(self, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        return _run_oops(["requirements", "check"], cwd=path)


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
        resizable=True,
        confirm_close=True,
    )
    # js_api calls run off the GUI thread, so a blocking command won't freeze
    # the window — the JS side just awaits.
    webview.start(debug=debug, gui="qt")
