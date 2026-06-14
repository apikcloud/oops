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
import json
import shutil
import tempfile
import urllib.parse
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
from oops.core.paths import UI, project_kb_path
from oops.kb.store import KBReader
from oops.output.base import RenderTarget
from oops.output.descriptors import load_descriptors
from oops.output.serializers import to_json_string
from oops.services.git import require_repository
from oops.services.project import require_project


def source_roots_from_payload(payload: dict) -> dict:
    """Build module_name → parent_dir from the payload's inventory paths.

    Each module node in the payload carries ``inventory.path`` — the absolute,
    resolved real path to the module directory as computed at analysis time.
    The parent of that directory is the root needed to reconstruct the absolute
    path from the module-relative ``source_file`` (``"<module>/sub/file.py"``).

    Preferred over the KB-based approach because inventory paths are always
    fresh (computed at payload-build time) and do not depend on paths stored
    in the KB at an earlier scan.
    """
    roots: dict = {}
    for mod in payload.get("modules", []):
        inv = mod.get("inventory") or {}
        path = inv.get("path", "")
        name = mod.get("module")
        if path and name:
            roots[name] = str(Path(path).parent)
    return roots


def _resolve_module_root(name: str, tier_root: Path) -> str | None:
    """Return the parent directory of ``name`` inside ``tier_root``.

    Tries flat layout first (``tier_root/name``), then one level deeper
    (``tier_root/*/name``) to cover OCA-style nested repos where modules live
    inside a repo subdirectory (e.g. ``.third-party/sale-workflow/module``).
    Returns ``None`` when the module directory cannot be located.
    """
    if (tier_root / name).is_dir():
        return str(tier_root)
    for candidate in sorted(tier_root.glob(f"*/{name}")):
        if candidate.is_dir():
            return str(candidate.parent)
    return None


def _build_source_roots(repo_path: Path) -> dict:
    """Map module_name → parent dir of the module using the project KB.

    Fallback when the payload is not available (e.g. dashboard before first
    ``doc_project`` call). The returned root is the directory that, when joined
    with the module-relative ``source_file`` (``"<module>/sub/file.py"``), gives
    the absolute path. Returns an empty dict when the KB does not exist yet.
    """
    kb_path = project_kb_path(repo_path)
    if not kb_path.exists():
        return {}
    with KBReader(kb_path) as kb:
        modules = kb.get_modules()    # {name: {origin: str, ...}}
        sources = kb.get_sources()    # {origin: abs_path_str}
    roots = {}
    for name, info in modules.items():
        origin = info.get("origin")
        if origin not in sources:
            continue
        root = _resolve_module_root(name, Path(sources[origin]))
        if root is not None:
            roots[name] = root
    return roots


def _read_source_slice(roots: dict, file: str, start: int, end: int) -> tuple[int, dict]:
    """Resolve a module-relative ``file`` path and return a line slice.

    ``start``/``end`` are 1-indexed inclusive; ``end <= 0`` means "to EOF".
    Returns ``(status_code, body_dict)`` — callers write the dict as JSON.
    Security: path-traversal attempts are rejected with a 403.
    """
    if not file:
        return 400, {"error": "missing file param"}

    module = file.split("/")[0]
    root_str = roots.get(module)
    if root_str is None:
        return 404, {"error": f"unknown module: {module!r}"}

    root = Path(root_str)
    abs_path = root / file
    try:
        abs_path.resolve().relative_to(root.resolve())
    except ValueError:
        return 403, {"error": "path traversal denied"}

    if not abs_path.is_file():
        return 404, {"error": f"not found: {file!r}"}

    try:
        lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return 500, {"error": str(exc)}

    s = max(0, start - 1)           # 1-indexed → 0-indexed
    if end > 0:
        e = end
    else:
        # end unknown (source_end_line NULL in KB for Odoo core): detect function
        # boundary by scanning for the next def/class/@ at the same indent level.
        e = len(lines)
        if s < len(lines):
            def_indent = len(lines[s]) - len(lines[s].lstrip())
            for i in range(s + 1, len(lines)):
                stripped = lines[i].strip()
                if not stripped:
                    continue
                curr_indent = len(lines[i]) - len(lines[i].lstrip())
                if curr_indent <= def_indent and (
                    stripped.startswith(("def ", "class ", "async def ", "@"))
                ):
                    e = i
                    break
    return 200, {"code": "\n".join(lines[s:e]), "file": file}


def _make_handler(site_dir: str, source_roots: dict):
    """Return a partial HTTP handler with a ``/api/source`` endpoint.

    The endpoint accepts ``?file=<module-relative-path>&start=<int>&end=<int>``
    and returns ``{"code": "<source text>", "file": "<path>"}`` as JSON.
    ``start`` and ``end`` are 1-indexed line numbers (inclusive).
    Unknown modules and path-traversal attempts return 4xx errors.
    """

    class _Handler(http.server.SimpleHTTPRequestHandler):
        _roots: dict = source_roots

        def do_GET(self) -> None:
            if self.path.startswith("/api/source"):
                self._serve_source()
            else:
                super().do_GET()

        def _serve_source(self) -> None:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            file  = (params.get("file")  or [""])[0]
            start = int((params.get("start") or ["1"])[0])
            end   = int((params.get("end")   or ["-1"])[0])

            status, payload = _read_source_slice(self._roots, file, start, end)
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            if args and "/api/source" in str(args[0]):
                return
            super().log_message(fmt, *args)

    return functools.partial(_Handler, directory=site_dir)


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

    source_roots = source_roots_from_payload(payload)

    with tempfile.TemporaryDirectory(prefix="oops-serve-") as tmp:
        site = prepare_site_dir(payload, Path(tmp))
        handler = _make_handler(str(site), source_roots)
        with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/"
            click.echo(f"Serving project docs at {url} (Ctrl-C to stop)", err=True)
            if not no_browser:
                webbrowser.open(url)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                raise EarlyExit() from None
