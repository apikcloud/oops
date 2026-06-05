# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/depends/show.py


from collections import defaultdict, deque
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.compat import Optional
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.io.file import enrich_addon, find_addons, parse_odoo_version
from oops.output.formatters import DependsReportFormatter, FormatterRegistry, JsonFormatter
from oops.output.sinks import deliver
from oops.services.git import list_submodules, require_repository
from oops.services.kb import load_odoo_kb, require_kb
from oops.utils.render import ask

from .presenters.show import ShowPresenter

FORMATTERS: FormatterRegistry = {
    "json": JsonFormatter,
    "html": DependsReportFormatter,
}


@command(name="show", help=__doc__)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "html"]),
    default="html",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
@click.pass_context
def main(ctx, output_format: str, output_path: Optional[Path]) -> None:
    repo, repo_path = require_repository()

    metadata = get_metadata()
    formatter = FORMATTERS[output_format]()

    result: Result[dict] = Result()
    result.data = {"addons": [], "metrics": {}}

    # 1. Resolve Odoo version (with prompt fallback).
    version: Optional[str] = None
    try:
        image_info = parse_odoo_version(repo_path)
        version = str(image_info.major_version)
    except (FileNotFoundError, ValueError) as exc:
        result.add_warning(str(exc) or "Could not parse Odoo version.")

    if not version:
        version = ask("Odoo version")

    require_kb(version)

    # 2. Long-running processing.
    with live_progress("Initialisation..."):
        odoo_kb = load_odoo_kb(version)
        subs = list_submodules(repo)

        # 2a. Collect local addons.
        for addon in find_addons(repo_path, shallow=True):
            log.info(f"Enrichment of {addon.technical_name}")
            sub = subs.get(addon.rel_path, {})
            enrich_addon(addon, sub)
            result.data["addons"].append(
                {
                    "name": addon.technical_name,
                    "depends": addon.depends,
                    "origin": addon.classification,
                    "location": addon.location,
                }
            )

        # 2b. Walk the dependency chain to pull required Odoo modules.
        truly_unresolved = expand_to_transitive_closure(result.data["addons"], odoo_kb)
        if truly_unresolved:
            result.add_warning(
                f"{len(truly_unresolved)} modules referenced but not found: {', '.join(truly_unresolved)}"
            )

        # 2c. Compute transitive metrics on the closed graph.
        graph_stats = compute_dependency_metrics(result.data["addons"])

    # 3. Build the payload.
    result.data["metrics"] = {
        "total": len(result.data["addons"]),
        "by_origin": _count_by_origin(result.data["addons"]),
        "roots": graph_stats["roots"],
        "leaves_count": len(graph_stats["leaves"]),
        "unresolved": truly_unresolved,
    }

    # 4. Prepare for the chosen audience and render.
    output = ShowPresenter().prepare(result, target=formatter.target, metadata=metadata)
    deliver(formatter, output, output_format, output_path)


# ---------------------------------------------------------------------------
# Graph expansion — pull in transitively required Odoo modules
# ---------------------------------------------------------------------------


def expand_to_transitive_closure(
    addons: "list[dict]",
    odoo_kb: dict,
) -> "list[str]":
    """Expand `addons` in-place with all transitively required modules.

    Walks each addon's depends chain, pulling missing dependencies from
    `odoo_kb` until no new module can be added.

    Returns:
        Sorted list of module names that were referenced but neither in
        the initial addons nor in odoo_kb.
    """
    known = {a["name"] for a in addons}
    queue: deque[str] = deque()

    for addon in addons:
        for dep in addon["depends"]:
            if dep not in known:
                queue.append(dep)

    unresolved: set[str] = set()

    while queue:
        name = queue.popleft()
        if name in known:
            continue

        kb_entry = odoo_kb.get(name)
        if kb_entry is None:
            unresolved.add(name)
            known.add(name)  # mark as seen to avoid re-queueing
            continue

        addons.append(
            {
                "name": name,
                "depends": kb_entry["depends"],
                "origin": kb_entry["origin"],
                "location": None,
            }
        )
        known.add(name)

        for dep in kb_entry["depends"]:
            if dep not in known:
                queue.append(dep)

    return sorted(unresolved)


# ---------------------------------------------------------------------------
# Graph metrics — computed on the closed dataset
# ---------------------------------------------------------------------------


def compute_dependency_metrics(addons: "list[dict]") -> dict:
    """Augment each addon in-place with transitive metrics.

    Adds to each addon:
        ancestors_count: number of transitive dependencies (modules I need).
        descendants_count: number of transitive dependents (modules needing me).
        depth: longest path to a root (module with no in-set depends).
        reverse_depth: longest path to a leaf (module with no in-set dependents).
            0 for a leaf, higher for modules deep in the dependency stack.
        missing_deps: declared deps that are not in the addons list.

    Returns:
        Global stats: roots (no in-set depends), leaves (nobody depends on them).
    """
    by_name = {a["name"]: a for a in addons}
    all_names = set(by_name)

    forward: dict[str, set[str]] = {a["name"]: set(a["depends"]) for a in addons}
    reverse: dict[str, set[str]] = defaultdict(set)
    for name, deps in forward.items():
        for dep in deps:
            reverse[dep].add(name)

    for addon in addons:
        addon["missing_deps"] = sorted(set(addon["depends"]) - all_names)

    def transitive_count(start: str, graph: "dict[str, set[str]]") -> int:
        seen: set[str] = set()
        queue: deque[str] = deque([start])
        while queue:
            node = queue.popleft()
            for nxt in graph.get(node, ()):
                if nxt in seen or nxt not in all_names:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return len(seen)

    depth_cache: dict[str, int] = {}

    def compute_depth(name: str, visiting: "set[str]") -> int:
        if name in depth_cache:
            return depth_cache[name]
        if name in visiting:
            return 0  # cycle guard
        visiting.add(name)
        deps = forward.get(name, set()) & all_names
        d = 0 if not deps else 1 + max(compute_depth(x, visiting) for x in deps)
        visiting.discard(name)
        depth_cache[name] = d
        return d

    reverse_depth_cache: dict[str, int] = {}

    def compute_reverse_depth(name: str, visiting: "set[str]") -> int:
        """Longest path to a leaf (module with no in-set dependents).

        0 for a leaf, 1 + max(reverse_depth of dependents) otherwise.
        """
        if name in reverse_depth_cache:
            return reverse_depth_cache[name]
        if name in visiting:
            return 0  # cycle guard
        visiting.add(name)
        dependents = reverse.get(name, set()) & all_names
        d = 0 if not dependents else 1 + max(compute_reverse_depth(x, visiting) for x in dependents)
        visiting.discard(name)
        reverse_depth_cache[name] = d
        return d

    for addon in addons:
        name = addon["name"]
        addon["ancestors_count"] = transitive_count(name, forward)
        addon["descendants_count"] = transitive_count(name, reverse)
        addon["depth"] = compute_depth(name, set())
        addon["reverse_depth"] = compute_reverse_depth(name, set())

    return {
        "roots": sorted(n for n, deps in forward.items() if not (deps & all_names)),
        "leaves": sorted(n for n in by_name if not reverse.get(n)),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_by_origin(addons: "list[dict]") -> "dict[str, int]":
    counts: dict[str, int] = defaultdict(int)
    for addon in addons:
        counts[addon["origin"]] += 1
    return dict(counts)
