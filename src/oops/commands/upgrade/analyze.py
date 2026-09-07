# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""
Observe the repository at the source ref and write state.yml.

Deterministic and regenerable: lists every module at the repo root and its
classification (custom / oca / third-party) plus the dependency graph from
source manifests. Never edited by hand — this is the machine-owned ground
truth the plan is seeded from.

By default also probes upstream availability via the GitHub API for OCA and
third-party modules (disable with --no-probe-upstream). When a module is
confirmed available upstream, its TARGET manifest deps are also fetched in
the same API call — these are stored as `target_depends_on` in state.yml
and used by `plan` to detect new required modules in the target version.
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
from oops.io.file import parse_odoo_version
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
    SpaReportFormatter,
)
from oops.services.git import list_submodules, require_repository
from oops.services.github import fetch_manifest_deps_rest
from oops.utils.render import warn_experimental
from oops_engine.addons import dedup_addons_by_path, enrich_addon_from_subs
from oops_engine.models import Result

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
    "html": SpaReportFormatter,
}


@command(name="analyze", help=__doc__)
@click.option(
    "--source-ref",
    default=None,
    help="Label for this snapshot (default: current branch/HEAD).",
)
@click.option(
    "--from",
    "from_version",
    default=None,
    help="Source Odoo version (e.g. 18.0).",
)
@click.option(
    "--to",
    "to_version",
    default=None,
    help="Target Odoo version (e.g. 19.0).",
)
@click.option(
    "--probe-upstream/--no-probe-upstream",
    default=True,
    help=(
        "Check upstream availability via GitHub API (default: on). "
        "Also fetches target manifest deps for confirmed pull modules. "
        "Disable with --no-probe-upstream for a fast, fully offline run."
    ),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "html"]),
    default="text",
    show_default=True,
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
)
@click.pass_context
def main(
    ctx,
    source_ref,
    from_version,
    to_version,
    probe_upstream,
    output_format,
    output_path,
):
    """Snapshot the repository and write state.yml."""
    warn_experimental()
    token: str = (ctx.obj or {}).get("token", "")
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()
    repo, repo_path = require_repository()

    # Resolve source_ref.
    if not source_ref:
        try:
            source_ref = repo.active_branch.name
        except TypeError:
            source_ref = repo.git.rev_parse("HEAD", short=True)

    # Resolve from_version.
    if not from_version:
        from_version = config.manifest.odoo_version or ""
        if not from_version:
            try:
                from_version = str(parse_odoo_version(repo_path).major_version)
            except (ValueError, OSError):
                from_version = ""
        if not from_version:
            m = re.search(r"\b(\d+\.\d+)\b", source_ref)
            if m:
                from_version = m.group(1)
    if not from_version:
        raise OopsError(
            "Cannot detect source Odoo version. Provide --from (e.g. --from 18.0), "
            f"set manifest.odoo_version in .oops.yaml, or check {config.project.file_odoo_version}."
        )
    if not to_version:
        raise OopsError("Target version required. Provide --to (e.g. --to 19.0).")

    # `metadata.parameters` was snapshotted from raw CLI options before this
    # callback resolved source_ref/from_version/to_version — refresh it so
    # presenters (e.g. the HTML report's version indicator) see the actual
    # values used, not the CLI defaults (None).
    if metadata is not None:
        metadata.parameters.update(
            {"source_ref": source_ref, "from_version": from_version, "to_version": to_version}
        )

    sub_meta_by_relpath = list_submodules(repo)
    modules: dict[str, ModuleState] = {}

    # --- Phase 1: local observation (deterministic, no network) ---
    with live_progress(f"Analysing repository at {source_ref}…"):
        seen = dedup_addons_by_path(repo_path, shallow=True)

        for addon in seen.values():
            if not addon.root:
                continue
            enrich_addon_from_subs(
                addon,
                sub_meta_by_relpath,
                author=config.manifest.author,
                prefix=config.project.prefix,
                owner=config.github.owner,
            )
            sub_meta = sub_meta_by_relpath.get(addon.rel_path, {})
            kind, repo_slug = classify_origin(addon, sub_url=sub_meta.get("url"))
            modules[addon.technical_name] = ModuleState(
                name=addon.technical_name,
                origin=Origin(kind=kind, repo=repo_slug, ref=addon.branch or None),
                depends_on=list(dict.fromkeys(addon.depends)),
                # target_depends_on: None until the probe fills it in.
            )

    # --- Phase 2: upstream probe (network, opt-out) ---
    # Fills upstream_available, upstream_prs, AND target_depends_on for
    # confirmed pull modules — all in the same API calls, no extra cost.
    if probe_upstream:
        log.info("Probing upstream availability and fetching target manifest deps…")
        _probe_modules(modules, to_version, token)
    else:
        log.info(
            "Upstream probe skipped (--no-probe-upstream). "
            "target_depends_on will be empty; `plan` may miss ghost modules."
        )

    # --- Phase 3: write state.yml ---
    state = State(
        version=2,
        source_ref=source_ref,
        from_version=from_version,
        to_version=to_version,
        modules=modules,
    )
    state_path = artifact_path(repo_path, STATE_FILE)
    save_state(state_path, state)

    # --- Phase 4: report ---
    probed = sum(1 for m in modules.values() if m.upstream_available is not None)
    with_target_deps = sum(1 for m in modules.values() if m.target_depends_on is not None)

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
            # Probe results — 0 when --no-probe-upstream.
            "upstream_available": sum(1 for m in modules.values() if m.upstream_available is True),
            "upstream_missing": sum(1 for m in modules.values() if m.upstream_available is False),
            "not_probed": len(modules) - probed,
            "target_deps_fetched": with_target_deps,
        },
    }

    output = AnalyzePresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)


# ---------------------------------------------------------------------------
# Upstream probe — fills upstream_available, upstream_prs, target_depends_on
# ---------------------------------------------------------------------------


def _probe_modules(modules: dict, to_version: str, token: "str | None") -> None:
    """Probe OCA and third-party modules against their upstream repo.

    Mutates ModuleState objects in place.

    With token    → 2 GraphQL queries total (availability + PR search).
    Without token → 1 REST call per unique repo + 1 per absent module.

    In both paths, target_depends_on is filled for confirmed-available modules
    (upstream_available=True) by fetching the target manifest. This is done in
    the same API round-trip where possible to avoid extra calls.

    On any fetch failure, the affected module's upstream_available stays None
    (not probed) — the plan will mark it review=True.
    """
    modules_by_repo: dict[str, list[str]] = {}
    for ms in modules.values():
        if ms.origin.kind not in ("oca", "third-party") or not ms.origin.repo:
            continue
        modules_by_repo.setdefault(ms.origin.repo, []).append(ms.name)

    if not modules_by_repo:
        return

    if token:
        _probe_graphql(modules, modules_by_repo, to_version, token)
    else:
        _probe_rest(modules, modules_by_repo, to_version)


def _probe_graphql(
    modules: dict,
    modules_by_repo: dict,
    to_version: str,
    token: str,
) -> None:
    """GraphQL path: availability + target deps in 2 queries, PR search in 1 more."""
    from oops.services.github import (
        check_upstream_graphql,
        fetch_target_deps_graphql,
        search_prs_graphql,
    )

    # Query 1: availability — which modules exist on the target branch?
    try:
        available = check_upstream_graphql(modules_by_repo, to_version, token)
    except Exception as exc:
        log.warning(f"GraphQL upstream check failed ({exc}); falling back to REST.")
        _probe_rest(modules, modules_by_repo, to_version)
        return

    absent_by_repo: dict[str, list[str]] = {}
    available_by_repo: dict[str, list[str]] = {}

    for ms in modules.values():
        if ms.name not in available:
            continue
        ms.upstream_available = available[ms.name]
        if ms.upstream_available and ms.origin.repo:
            available_by_repo.setdefault(ms.origin.repo, []).append(ms.name)
        elif not ms.upstream_available and ms.origin.repo:
            absent_by_repo.setdefault(ms.origin.repo, []).append(ms.name)

    # Query 2: target manifest deps for confirmed-available modules.
    # Fetched in bulk per repo to minimise GraphQL cost.
    if available_by_repo:
        try:
            target_deps = fetch_target_deps_graphql(available_by_repo, to_version, token)
            for ms in modules.values():
                if ms.name in target_deps:
                    ms.target_depends_on = target_deps[ms.name]
        except Exception as exc:
            log.warning(
                f"GraphQL target deps fetch failed ({exc}). "
                "target_depends_on will be empty for pull modules — "
                "ghost detection in `plan` may be incomplete."
            )

    # Query 3: search for open PRs on absent modules.
    if absent_by_repo:
        try:
            prs = search_prs_graphql(absent_by_repo, to_version, token)
            for ms in modules.values():
                if ms.name in prs:
                    ms.upstream_prs = prs[ms.name]
        except Exception as exc:
            log.warning(f"GraphQL PR search failed: {exc}")


def _probe_rest(
    modules: dict,
    modules_by_repo: dict,
    to_version: str,
) -> None:
    """REST fallback: 1 call per repo for availability + 1 per available module
    for its target manifest deps + 1 per absent module for PR search."""
    from oops.services.github import (
        list_remote_addons,
        search_upstream_prs,
    )

    # Pass 1: availability — list addons per repo on the target branch.
    repo_cache: dict[str, "set[str] | None"] = {}
    for repo_key in modules_by_repo:
        try:
            owner, repo_name = repo_key.split("/", 1)
            repo_cache[repo_key] = set(list_remote_addons(owner, repo_name, to_version, ""))
        except Exception as exc:
            log.warning(f"REST availability check failed for {repo_key}: {exc}")
            repo_cache[repo_key] = None

    for ms in modules.values():
        if ms.origin.kind not in ("oca", "third-party") or not ms.origin.repo:
            continue
        addon_set = repo_cache.get(ms.origin.repo)
        if addon_set is None:
            continue  # fetch failed — upstream_available stays None
        ms.upstream_available = ms.name in addon_set

    # Pass 2: target manifest deps for confirmed-available modules.
    # One REST call per module (Trees API on the target branch manifest file).
    # Grouped to share the repo_cache already built above.
    for ms in modules.values():
        if not ms.upstream_available or not ms.origin.repo:
            continue
        try:
            owner, repo_name = ms.origin.repo.split("/", 1)
            ms.target_depends_on = fetch_manifest_deps_rest(owner, repo_name, ms.name, to_version)
        except Exception as exc:
            log.warning(f"Could not fetch target manifest for {ms.name} ({ms.origin.repo}@{to_version}): {exc}")
            # target_depends_on stays None — plan will handle gracefully.

    # Pass 3: PR search for absent modules.
    for ms in modules.values():
        if ms.upstream_available is not False or not ms.origin.repo:
            continue
        try:
            owner, repo_name = ms.origin.repo.split("/", 1)
            ms.upstream_prs = search_upstream_prs(owner, repo_name, ms.name, to_version, None)
        except Exception:
            pass
