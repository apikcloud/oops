# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""
Observe the repository at the source ref and write state.yml.

Deterministic and regenerable: lists every module at the repo root and its
classification (custom / oca / third-party) plus the dependency graph from
manifests. Never edited by hand — this is the machine-owned ground truth the
plan is seeded from.

By default also checks (via the GitHub API) whether a target version appears to
exist upstream for OCA and third-party modules. Disable with --no-probe-upstream.
"""

from __future__ import annotations

import re
from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import AddonInfo, Result
from oops.io.file import enrich_addon, find_addons
from oops.output.formatters import FormatterRegistry, JsonFormatter, OutputFormatter, SimpleSummaryConsoleFormatter
from oops.services.git import list_submodules, require_repository

from .common import (
    STATE_FILE,
    ModuleState,
    Origin,
    State,
    artifact_path,
    classify_origin,
    save_state,
)
from .presenters.analyze import AnalyzePresenter

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="analyze", help=__doc__)
@click.option("--source-ref", default=None, help="Label for this snapshot (default: current branch/HEAD).")
@click.option("--from", "from_version", default=None, help="Source Odoo version (e.g. 18.0).")
@click.option("--to", "to_version", default=None, help="Target Odoo version (e.g. 19.0).")
@click.option(
    "--probe-upstream/--no-probe-upstream",
    default=True,
    help="Check upstream availability via GitHub API (default: on). Disable with --no-probe-upstream.",
)
@click.option(
    "--token", default=None, envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token (raises rate limits and enables private repos).",
)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--output-path", "output_path", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.pass_context
def main(ctx, source_ref, from_version, to_version, probe_upstream, token, output_format, output_path):
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()
    repo, repo_path = require_repository()

    if not source_ref:
        try:
            source_ref = repo.active_branch.name
        except TypeError:
            source_ref = repo.git.rev_parse("HEAD", short=True)

    if not from_version:
        from_version = config.manifest.odoo_version or ""
        if not from_version:
            m = re.search(r"\b(\d+\.\d+)\b", source_ref)
            if m:
                from_version = m.group(1)
    if not from_version:
        raise OopsError("Cannot detect source Odoo version. Provide --from (e.g. --from 18.0).")
    if not to_version:
        raise OopsError("Target version required. Provide --to (e.g. --to 19.0).")

    sub_meta_by_relpath = list_submodules(repo)

    modules: dict[str, ModuleState] = {}

    with live_progress(f"Analysing repository at {source_ref}…"):
        # Dedup by resolved path, preferring root symlinks (mirrors list.py).
        seen: dict[str, AddonInfo] = {}
        for addon in find_addons(repo_path, shallow=True):
            if addon.path not in seen or addon.symlinked:
                seen[addon.path] = addon

        for addon in seen.values():
            if not addon.root:
                continue
            sub_meta = sub_meta_by_relpath.get(addon.rel_path, {})
            enrich_addon(addon, sub_meta)
            kind, repo_slug = classify_origin(addon)
            origin = Origin(
                kind=kind,
                repo=repo_slug,
                ref=addon.branch or None,
            )
            modules[addon.technical_name] = ModuleState(
                name=addon.technical_name,
                origin=origin,
                depends_on=addon.depends,
            )

    if probe_upstream:
        log.info("Probing upstream availability…")
        _probe_modules(modules, to_version, token)

    state = State(
        version=2,
        source_ref=source_ref,
        from_version=from_version,
        to_version=to_version,
        modules=modules,
    )
    state_path = artifact_path(repo_path, STATE_FILE)
    save_state(state_path, state)

    result: Result[dict] = Result()
    result.data = {
        "cmd": f"Analyze {from_version} → {to_version}",
        "source_ref": source_ref,
        "state_path": str(state_path),
        "modules": modules,
        "metrics": {
            "total": len(modules),
            "custom": sum(1 for m in modules.values() if m.origin.kind == "custom"),
            "oca": sum(1 for m in modules.values() if m.origin.kind == "oca"),
            "third_party": sum(1 for m in modules.values() if m.origin.kind == "third-party"),
        },
    }

    output = AnalyzePresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)


def _probe_modules(modules: dict, to_version: str, token: str | None) -> None:
    """Probe OCA and third-party modules against their upstream repo. Mutates in place.

    Fetches each unique repo's addon list exactly once (cached), then checks
    individual modules against it. Only searches PRs for absent modules.
    On fetch failure the module's upstream_available stays None (not probed).
    """
    from oops.services.github import list_remote_addons, search_upstream_prs

    # One list_remote_addons call per unique (owner/repo, branch) pair.
    # None = fetch failed; set[str] = addon names present on target branch.
    repo_cache: dict[str, set[str] | None] = {}

    for ms in modules.values():
        if ms.origin.kind not in ("oca", "third-party") or not ms.origin.repo:
            continue
        repo_key = ms.origin.repo
        if repo_key in repo_cache:
            continue
        try:
            owner, repo_name = repo_key.split("/", 1)
            repo_cache[repo_key] = set(list_remote_addons(owner, repo_name, to_version, token or ""))
        except Exception:
            repo_cache[repo_key] = None  # fetch failed → leave as "not probed"

    for ms in modules.values():
        if ms.origin.kind not in ("oca", "third-party") or not ms.origin.repo:
            continue
        addon_set = repo_cache.get(ms.origin.repo)
        if addon_set is None:
            continue  # fetch failed → upstream_available stays None
        ms.upstream_available = ms.name in addon_set
        if not ms.upstream_available:
            try:
                owner, repo_name = ms.origin.repo.split("/", 1)
                ms.upstream_prs = search_upstream_prs(owner, repo_name, ms.name, to_version, token)
            except Exception:
                pass
