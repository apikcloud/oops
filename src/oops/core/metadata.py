# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: metadata.py — src/oops/core/metadata.py

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from oops.core.compat import Any, Dict, Optional

UTC = timezone.utc


def _resolve_tool_version() -> str:
    try:
        return "v" + version("oops")
    except PackageNotFoundError:
        return "latest"


@dataclass
class Metadata:
    """Describes the execution context of a command.

    Belongs to Output, applied to the whole payload, used by every formatter.
    """

    command: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    odoo_version: Optional[str] = None
    kb_global_path: Optional[str] = None
    kb_global_ts: Optional[datetime] = None
    kb_project_ts: Optional[datetime] = None
    git_branch: Optional[str] = None
    git_commit: Optional[str] = None
    parameters: dict[str, Any] = field(default_factory=dict)
    tool_version: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["generated_at"] = self.generated_at.isoformat()
        d["kb_global_ts"] = self.kb_global_ts.isoformat() if self.kb_global_ts else None
        d["kb_project_ts"] = self.kb_project_ts.isoformat() if self.kb_project_ts else None
        return d


def collect_metadata(
    command: str,
    repo_path: Optional[Path] = None,
    odoo_version: Optional[str] = None,
    parameters: "Optional[Dict[str, Any]]" = None,
) -> Metadata:
    """Collect execution metadata. Fills git info from repo_path if provided."""
    meta = Metadata(
        command=command,
        odoo_version=odoo_version,
        parameters=parameters or {},
        tool_version=_resolve_tool_version(),
    )
    if repo_path is not None:
        meta.project_path = str(repo_path)
        meta.project_name = repo_path.name

    return meta


def get_metadata() -> "Optional[Metadata]":
    import click

    ctx = click.get_current_context(silent=True)
    if ctx is not None and isinstance(ctx.obj, dict) and "metadata" in ctx.obj:
        return ctx.obj["metadata"]
    return None
