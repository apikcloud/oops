# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: api.py — src/oops/dashboard/api.py

from __future__ import annotations

from pathlib import Path

from oops.io.tools import run_oops

CHECK_COMMANDS: "list[tuple[list[str], str]]" = [
    (["project", "check"], "Project check"),
    (["requirements", "check"], "Requirements check"),
    (["submodules", "check"], "Submodules check"),
]


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
        return run_oops(["addons", "list"], cwd=path)

    def analyze_module(self, module_path: str, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        return run_oops(["addons", "analyze", module_path], cwd=path)

    def check_project(self, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        return run_oops(["project", "check"], cwd=path)

    def check_requirements(self, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        return run_oops(["requirements", "check"], cwd=path)

    def check_all(self, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        sections: list[dict] = []
        for args, title in CHECK_COMMANDS:
            payload = run_oops(args, cwd=path)
            sections.append(
                {
                    "command": " ".join(args),
                    "title": title,
                    "data": payload.get("data", []),
                    "warnings": payload.get("warnings", []),
                    "errors": payload.get("errors", []),
                    "error": payload.get("error"),
                }
            )
        return {"metadata": {"command": "checks"}, "sections": sections}

    def doc_project(self, path: "str | None" = None) -> dict:
        from pathlib import Path  # noqa: PLC0415

        from git import Repo  # noqa: PLC0415
        from oops.commands.project.serve import build_payload  # noqa: PLC0415

        p = path or self._project_path
        if not p:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        try:
            repo = Repo(p, search_parent_directories=True)
            return build_payload(repo, Path(p), show_all=False, names=(), refresh=False)
        except Exception as exc:
            return {"metadata": {"command": "error"}, "error": str(exc)}

    def project_info(self, path: "str | None" = None) -> dict:
        path = path or self._project_path
        if not path:
            return {"metadata": {"command": "error"}, "error": "no project selected"}
        return run_oops(["project", "show"], cwd=path)
