# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""
Observe the repository at the source ref and write state.yml.

Deterministic and regenerable: lists every module and its origin
(local / submodule / oca / core) plus the dependency graph computed from
manifests. Never edited by hand — this is the machine-owned ground truth
the plan is seeded from.

With --probe-upstream, also checks (via the GitHub API) whether a target
version appears to exist upstream for OCA/submodule modules. This step is
opt-in because it is slow, network-dependent and may be stale.
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
from oops.core.models import Result
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
@click.option("--probe-upstream", is_flag=True, help="Check upstream availability via GitHub (slow, opt-in).")
@click.option(
    "--token", default=None, envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    help="GitHub token (required for --probe-upstream on private repos; raises rate limits).",
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
        for addon in find_addons(repo_path):
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
        _probe_oca_modules(modules, to_version, token)

    all_dep_names = {dep for ms in modules.values() for dep in ms.depends_on}
    for dep in sorted(all_dep_names):
        if dep not in modules:
            modules[dep] = ModuleState(name=dep, origin=Origin(kind="core"))

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
            "local": sum(1 for m in modules.values() if m.origin.kind == "local"),
            "oca": sum(1 for m in modules.values() if m.origin.kind == "oca"),
            "submodule": sum(1 for m in modules.values() if m.origin.kind == "submodule"),
            "core": sum(1 for m in modules.values() if m.origin.kind == "core"),
        },
    }

    output = AnalyzePresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)


def _probe_oca_modules(modules: dict, to_version: str, token: str | None) -> None:
    """Probe each OCA module against its upstream repo. Mutates modules in place."""
    from oops.services.github import check_upstream_module

    for ms in modules.values():
        if ms.origin.kind != "oca" or not ms.origin.repo:
            continue
        try:
            owner, repo_name = ms.origin.repo.split("/", 1)
        except ValueError:
            continue
        probe = check_upstream_module(owner, repo_name, ms.name, to_version, token)
        ms.upstream_available = probe["available"]
        ms.upstream_prs = [pr["url"] for pr in probe["prs"]]
