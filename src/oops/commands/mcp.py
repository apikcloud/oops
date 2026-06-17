# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: mcp.py — src/oops/commands/mcp.py

"""
Read-only MCP server over the analysis pipeline. Optional extra: oops[mcp].
It does NOT re-implement analysis — it serves the same DocModel payload the
`project serve` / `project doc` commands already build, and only *derives* the
KB cache (never mutates the repo).
"""

from __future__ import annotations

from oops.commands.base import command
from oops.commands.project.serve import build_payload
from oops.core.compat import Any
from oops.core.exceptions import OopsError
from oops.output.serializers import to_json_string
from oops.services.git import require_repository
from oops.services.project import require_project

# Cached DocModel payload. Built lazily; warmed at launch in main().
_PAYLOAD: dict[str, Any] | None = None


def _payload(refresh: bool = False) -> dict[str, Any]:
    """Build (or rebuild) the analysis payload. Builds the KB if absent.

    Read-only w.r.t. the repo: only the derived KB cache may be (re)generated.
    Fails cleanly if the cwd is not an oops project — never inits it.
    """
    global _PAYLOAD
    if _PAYLOAD is None or refresh:
        repo, repo_path = require_repository()  # raises if not a git repo
        require_project(repo_path)  # raises if not an oops project
        _PAYLOAD = build_payload(repo, repo_path, show_all=True, names=(), refresh=refresh)
    return _PAYLOAD


def _freshness(payload: dict[str, Any]) -> dict[str, Any]:
    """What the client is reasoning over — so the agent knows if it's stale."""
    meta = payload.get("metadata", {})
    return {
        "kb_built_at": meta.get("kb_project_ts"),
        "generated_at": meta.get("generated_at"),
        "project": meta.get("project_name"),
        "odoo_version": meta.get("odoo_version"),
    }


def _build_server() -> Any:
    """Import FastMCP and register all resources/tools. Deferred so a missing
    `mcp` extra does not crash the CLI at import time."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:  # pragma: no cover
        raise OopsError(
            "The MCP SDK is required for `oops mcp`. Install with extra 'oops[mcp]'"
        ) from error

    mcp = FastMCP("oops")

    # ── Resource: project synthesis (read-only, no args) ────────────────────
    @mcp.resource("oops://overview")
    def project_overview() -> str:
        """High-level project synthesis: modules, models, and freshness.

        Entry point — gives the agent the valid identifiers (module / model names)
        to pass to describe_module / describe_model.
        """
        p = _payload()
        modules = p.get("modules", [])
        overview = {
            "freshness": _freshness(p),
            "module_count": len(modules),
            "model_count": len(p.get("models_by_bare", {})),
            "modules": [m.get("module") for m in modules],
            "models": sorted(p.get("models_by_bare", {}).keys()),
        }
        return to_json_string(overview)

    # ── Tool: aggregated view of a model across all modules ──────────────────
    @mcp.tool()
    def describe_model(model: str) -> dict[str, Any]:
        """Everything the project does to a model (e.g. 'sale.order'), aggregated
        across every contributing module: fields, methods, overrides, provenance.
        Use find() first if you don't know the exact model name.
        """
        p = _payload()
        entry = p.get("models_by_bare", {}).get(model)
        if entry is None:
            return {"error": f"unknown model '{model}'", "hint": "call find() to locate it"}
        return {"freshness": _freshness(p), "model": model, **entry}

    # ── Tool: what a single addon delivers ──────────────────────────────────
    @mcp.tool()
    def describe_module(module: str) -> dict[str, Any]:
        """Manifest, contributed models/fields/methods/views and dependencies of one
        addon (e.g. 'apik_crm')."""
        p = _payload()
        mod = next((m for m in p.get("modules", []) if m.get("module") == module), None)
        if mod is None:
            return {"error": f"unknown module '{module}'", "hint": "call find() to locate it"}
        return {"freshness": _freshness(p), **mod}

    # ── Tool: discovery (locate before describing) ───────────────────────────
    @mcp.tool()
    def find(query: str, limit: int = 25) -> dict[str, Any]:
        """Find modules, models and symbols whose name contains `query`
        (case-insensitive). Returns identifiers usable with the describe_* tools."""
        p = _payload()
        q = query.lower()
        modules = [m["module"] for m in p.get("modules", []) if q in m.get("module", "").lower()]
        models = [name for name in p.get("models_by_bare", {}) if q in name.lower()]
        symbols: list[dict[str, str]] = []
        for m in p.get("modules", []):
            for f in m.get("fields", []):
                if q in f.get("name", "").lower():
                    symbols.append({"kind": "field", "id": f.get("id", ""), "module": m["module"]})
            for meth in m.get("methods", []):
                if q in meth.get("name", "").lower():
                    symbols.append(
                        {"kind": "method", "id": meth.get("id", ""), "module": m["module"]}
                    )
        return {
            "freshness": _freshness(p),
            "modules": modules[:limit],
            "models": models[:limit],
            "symbols": symbols[:limit],
        }

    # ── Tool: explicit refresh (the only state-changing action — cache only) ─
    @mcp.tool()
    def refresh() -> dict[str, Any]:
        """Rebuild the knowledge base from the current code and return freshness.
        Use when the agent suspects the cached analysis is stale."""
        return {"freshness": _freshness(_payload(refresh=True)), "status": "refreshed"}

    return mcp


@command(name="mcp", help=__doc__)
def main() -> None:
    mcp = _build_server()
    mcp.run(transport="stdio")
