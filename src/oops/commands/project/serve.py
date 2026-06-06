# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: serve.py — oops/commands/project/serve.py

"""Serve a local single-page app for consulting project documentation.

Reuses the `oops project doc` data pipeline (inventory + IR v2 analysis →
DocModel), emits a single `data.js`, and serves a vendored, offline SPA via
the standard-library HTTP server. Read-only; no source rewriting.
"""
from __future__ import annotations

import functools
import http.server
import shutil
import tempfile
import webbrowser
from pathlib import Path

import click
from oops.commands.base import command
from oops.commands.project.doc import _build_inventory, _run_analyze
from oops.commands.project.presenters.doc import ProjectDocPresenter
from oops.core.exceptions import EarlyExit
from oops.core.logger import live_progress
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.core.paths import UI
from oops.output.base import RenderTarget
from oops.output.descriptors import load_descriptors
from oops.output.serializers import to_json_string
from oops.services.git import require_repository
from oops.services.project import require_project


def build_payload(
    repo, repo_path: Path, show_all: bool, names: tuple, refresh: bool
) -> dict:
    """Stages A–C → DocModel, plus the descriptor schema for client-side cards."""
    inventory = _build_inventory(repo, repo_path, show_all, names)
    if not inventory:
        raise EarlyExit()
    paths = [row["path"] for row in inventory.values()]
    ir = _run_analyze(paths, refresh)

    result: Result = Result()
    result.data = {"ir": ir, "inventory": inventory}

    target = RenderTarget(audience="machine", verbosity="full")
    output = ProjectDocPresenter().prepare(result, target=target, metadata=get_metadata())
    docmodel = output.layout
    cmd_meta = {k: v for k, v in output.metadata.to_dict().items() if v is not None} if output.metadata else {}
    merged_meta = {**docmodel.get("metadata", {}), **cmd_meta, "command": "project serve"}
    return {**docmodel, "metadata": merged_meta, "schema": load_descriptors()}


def prepare_site_dir(payload: dict, dest: Path) -> Path:
    """Copy UI assets into `dest` and write `data.js`."""
    shutil.copytree(str(UI), dest, dirs_exist_ok=True)
    (dest / "data.js").write_text(
        "window.OOPS = " + to_json_string(payload) + ";\n",
        encoding="utf-8",
    )
    return dest


@command(name="serve", help=__doc__)
@click.option("--all", "show_all", is_flag=True, help="Include inactive addons.")
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Force a project KB rebuild before analysis.",
)
@click.option(
    "--name", "-n", "names", multiple=True, help="Limit to these submodule names."
)
@click.option(
    "--port", type=int, default=0, show_default=True, help="Port (0 = pick a free one)."
)
@click.option("--no-browser", is_flag=True, help="Do not open the browser.")
def main(show_all, refresh, names, port, no_browser):
    repo, repo_path = require_repository()
    require_project(repo_path)

    with live_progress("Building documentation data..."):
        payload = build_payload(repo, repo_path, show_all, names, refresh)

    with tempfile.TemporaryDirectory(prefix="oops-serve-") as tmp:
        site = prepare_site_dir(payload, Path(tmp))
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(site)
        )
        with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/"
            click.echo(f"Serving project docs at {url} (Ctrl-C to stop)", err=True)
            if not no_browser:
                webbrowser.open(url)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                raise EarlyExit() from None
