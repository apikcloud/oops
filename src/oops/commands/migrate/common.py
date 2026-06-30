# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: common.py — src/oops/commands/migrate/common.py
#
# Shared helpers for the migrate workflow: artifact locations, load/save,
# and the dataclasses describing the three files (state / plan / status).
#
# Mental model (Terraform-like):
#   analyze → state.yml   machine-owned, deterministic, never hand-edited
#   plan    → plan.yml    human-owned intent, seeded from state, versioned
#   apply   → status.yml  machine-owned execution journal, re-runnable

from __future__ import annotations

import dataclasses
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from oops.core.compat import Literal, Optional

if TYPE_CHECKING:
    from oops.core.models import AddonInfo

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Action vocabulary — unambiguous on purpose (avoid update/upgrade).
# `keep` removed: what looked like keep is either `pull` (available upstream)
# or `port` with level=minimal (trivial porting). No module passes unchanged
# across a major Odoo version.
Action = Literal["pull", "port", "drop"]

# Origin kinds. `new` = module that doesn't exist on the source branch;
# added manually by the human or inserted by plan as a required dependency
# detected from target manifests.
OriginKind = Literal["custom", "oca", "third-party", "new"]

# Migration level — how deeply the module is ported. Human intent, not
# a machine operation. May drive default strategy selection in the future.
MigrationLevel = Literal["minimal", "partial", "full"]

# Calculated priority — derived from the dependency graph. Never hand-edited.
PriorityLevel = Literal["critical", "high", "normal", "anytime"]

# ---------------------------------------------------------------------------
# Built-in execution strategies
# Strategy = the set of mechanical commands apply() runs on a module.
# This is SEPARATE from level (which describes the expected human effort).
# ---------------------------------------------------------------------------

STRATEGIES: dict[str, list[str]] = {
    # Full mechanical pass: migrator + formatters + type hints.
    "standard": [
        "odoo-module-migrator",
        "pre-commit run --all-files",
        "pyupgrade --py310-plus **/*.py",
    ],
    # Migrator only — for modules with known fragile pre-commit setup.
    "minimal": [
        "odoo-module-migrator",
    ],
    # Branch + template commit only; the developer does everything manually.
    "none": [],
}

DEFAULT_STRATEGY = "standard"

# Priority thresholds (number of in-plan dependants).
# Tune per project if needed; these are reasonable defaults for ~20-50 modules.
CRITICAL_THRESHOLD = 5
HIGH_THRESHOLD = 2

# ---------------------------------------------------------------------------
# Artifact locations
# ---------------------------------------------------------------------------
#
# .oops/migrate/ is git-ignored EXCEPT plan.yml, which is versioned.
# state.yml and status.yml are regenerable; analyze is the mandatory
# entry point after a fresh clone.

ARTIFACT_DIR = Path(".oops") / "migrate"
STATE_FILE = ARTIFACT_DIR / "state.yml"
PLAN_FILE = ARTIFACT_DIR / "plan.yml"
STATUS_FILE = ARTIFACT_DIR / "status.yml"


def artifact_path(repo_path: Path, name: Path) -> Path:
    return repo_path / name


# ---------------------------------------------------------------------------
# Origin classification helper
# ---------------------------------------------------------------------------


def classify_origin(addon: "AddonInfo") -> "tuple[OriginKind, Optional[str]]":
    """Map an enriched AddonInfo to (OriginKind, repo_slug).

    Uses addon.classification directly (custom | oca | third-party).
    repo_slug is "owner/repo" (e.g. "OCA/server-tools") or None.
    Must be called AFTER enrich_addon().
    """
    from oops.utils.net import website_to_github_repo

    kind: OriginKind = addon.classification or "third-party"

    if kind == "custom":
        return ("custom", None)

    if addon.submodule:
        return (kind, addon.submodule)

    pair = website_to_github_repo(getattr(addon, "website", None))
    if pair:
        return (kind, f"{pair[0]}/{pair[1]}")

    return (kind, None)


# ---------------------------------------------------------------------------
# State dataclasses (machine-owned)
# ---------------------------------------------------------------------------


@dataclass
class Origin:
    """Where a module comes from. Machine field, refreshed on every plan."""

    kind: OriginKind
    repo: Optional[str] = None
    ref: Optional[str] = None
    pr: Optional[str] = None  # PR URL → oops pr add; absent → oops submodule add


@dataclass
class ModuleState:
    """Observed facts about one module at the source ref. Machine-owned."""

    name: str
    origin: Origin
    depends_on: list[str] = field(default_factory=list)
    # Deps read from the TARGET manifest (pull modules only).
    # None = not yet fetched (port modules, or probe not run).
    target_depends_on: Optional[list[str]] = None
    upstream_available: Optional[bool] = None  # None = not probed
    upstream_prs: list[dict] = field(default_factory=list)


@dataclass
class State:
    """state.yml — deterministic snapshot of the repo at source_ref."""

    version: int
    source_ref: str
    from_version: str
    to_version: str
    modules: dict[str, ModuleState] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Plan dataclasses (human-owned except machine fields noted below)
# ---------------------------------------------------------------------------


@dataclass
class ModulePlan:
    """One module's intent in the migration plan.

    Human-owned fields: action, level, strategy, group, tools, merge_with,
        rename, priority, reason, review, pr.
    Machine fields (refreshed on every `plan` run, never hand-edited):
        origin, depends_on, calculated_priority, descendant_count,
        resolved_branch, resolved_tools.

    IMPORTANT — absent vs explicitly emptied:
        tools=None   means "inherit defaults from plan.defaults"
        tools=[]     means "explicitly no tools for this module"
        The YAML round-trip must preserve this distinction (see load_plan /
        save_plan). Do NOT re-populate tools when it is an explicit [].
    """

    name: str

    # ---- human intent ----
    action: Optional[Action] = None  # must be set or plan refuses
    level: MigrationLevel = "full"  # effort expectation for the developer
    strategy: Optional[str] = None  # None = inherit from defaults
    group: Optional[str] = None
    tools: Optional[list[str]] = None  # None = inherit; [] = explicit none
    merge_with: Optional[dict] = None  # {"into": "<target_module>"}
    rename: Optional[str] = None
    priority: Optional[str] = None  # human override (e.g. "anytime")
    reason: Optional[str] = None  # for drop, or ghost modules
    review: bool = False
    pr: Optional[str] = None  # manual PR URL override; takes precedence over origin.pr in apply

    # ---- machine fields (set by plan, never written by human) ----
    origin: Optional[Origin] = None
    depends_on: list[str] = field(default_factory=list)
    calculated_priority: Optional[PriorityLevel] = None
    descendant_count: int = 0
    resolved_branch: Optional[str] = None  # final branch name after template
    resolved_tools: Optional[list[str]] = None  # final tool list after defaults

    @property
    def effective_priority(self) -> str:
        """Human override takes precedence over calculated."""
        return self.priority or self.calculated_priority or "normal"

    @property
    def effective_strategy(self) -> str:
        return self.strategy or DEFAULT_STRATEGY

    @property
    def effective_tools(self) -> list[str]:
        if self.resolved_tools is not None:
            return self.resolved_tools
        return list(STRATEGIES.get(self.effective_strategy, []))


@dataclass
class MigrationPlan:
    """plan.yml — the only hand-edited, versioned artifact."""

    version: int
    migration: dict  # from/to/source_ref/target_branch/strategy/branch_template
    defaults: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)
    modules: dict[str, ModulePlan] = field(default_factory=dict)


# Backward-compatible alias — use MigrationPlan in new code.
Plan = MigrationPlan
# ---------------------------------------------------------------------------
# Dependency graph helpers
# ---------------------------------------------------------------------------


def effective_depends_on(mp: ModulePlan, ms: Optional[ModuleState]) -> list[str]:
    """Return the deps to use for graph computation.

    pull modules: use target_depends_on if available (upstream manifest),
        because that's what they'll require in the target version.
    port/drop modules: use source depends_on (the existing manifest).
    new modules: no source manifest — return whatever is in the plan.
    """
    if mp.action == "pull" and ms is not None and ms.target_depends_on is not None:
        return ms.target_depends_on
    if ms is not None:
        return ms.depends_on
    return mp.depends_on


def build_graph(
    modules: dict[str, ModulePlan],
    states: dict[str, ModuleState],
) -> dict[str, list[str]]:
    """Build the effective dependency graph, filtered to in-plan modules only.

    Excludes Odoo core modules and modules whose action is `drop` (they are
    effective leaves — nothing depends on them in the target). `pull` modules
    are considered available and do not block their dependants.
    """
    plan_names = set(modules.keys())
    graph: dict[str, list[str]] = {}
    for name, mp in modules.items():
        ms = states.get(name)
        raw_deps = effective_depends_on(mp, ms)
        # Keep only deps that are in the plan and not dropped/core.
        filtered = list(
            dict.fromkeys(
                d for d in raw_deps if d in plan_names and modules[d].action != "drop"
            )
        )
        graph[name] = filtered
    return graph


def compute_descendant_counts(graph: dict[str, list[str]]) -> dict[str, int]:
    """Count how many in-plan modules depend on each module (directly or transitively).

    Uses a reverse BFS from each node. O(N²) worst case but fine for
    migration plans (typically <100 modules).
    """
    # Build reverse graph: for each module, who depends on it?
    reverse: dict[str, list[str]] = {name: [] for name in graph}
    for name, deps in graph.items():
        for dep in deps:
            if dep in reverse:
                reverse[dep].append(name)

    counts: dict[str, int] = {}
    for start in graph:
        # BFS over reverse graph from `start`
        visited: set[str] = set()
        queue: deque[str] = deque([start])
        while queue:
            node = queue.popleft()
            for dependent in reverse.get(node, []):
                if dependent not in visited:
                    visited.add(dependent)
                    queue.append(dependent)
        counts[start] = len(visited)
    return counts


def calculate_priority(descendant_count: int) -> PriorityLevel:
    if descendant_count >= CRITICAL_THRESHOLD:
        return "critical"
    if descendant_count >= HIGH_THRESHOLD:
        return "high"
    if descendant_count == 0:
        return "anytime"
    return "normal"


def resolve_branch(mp: ModulePlan, migration: dict, groups: dict) -> str:
    """Compute the final branch name for a module.

    Group exception: if the module belongs to a group that defines its own
    branch, use that. Otherwise apply branch_template.
    """
    if mp.group and mp.group in groups:
        group_branch = groups[mp.group].get("branch")
        if group_branch:
            return group_branch
    template: str = migration.get("branch_template", "{to}/{module}")
    return template.format(
        to=migration.get("to", ""),
        module=mp.rename or mp.name,
    )


def resolve_tools(mp: ModulePlan, defaults: dict) -> list[str]:
    """Resolve the final tool list for a module.

    Priority: explicit module.tools > module.strategy > defaults.strategy > DEFAULT_STRATEGY.
    tools=[] means explicitly empty — never overridden by defaults.
    tools=None means inherit.
    """
    if mp.tools is not None:
        return mp.tools  # explicit (may be [])
    strategy_name = mp.strategy or defaults.get(mp.action, {}).get("strategy") or DEFAULT_STRATEGY
    return list(STRATEGIES.get(strategy_name, []))


# ---------------------------------------------------------------------------
# Seed / guess helpers
# ---------------------------------------------------------------------------


def _guess_action(ms: ModuleState) -> Action:
    """Guess the migration action from observed state.

    custom  → always port (no upstream to pull from)
    oca/third-party + upstream available → pull
    oca/third-party + not available or unknown → port (may be wrong; review=True)
    """
    if ms.origin.kind == "custom":
        return "port"
    if ms.upstream_available is True or ms.upstream_prs:
        return "pull"
    return "port"


def _needs_review(ms: ModuleState, action: Action) -> bool:
    """True when the guessed action is uncertain — human must confirm."""
    if ms.origin.kind == "custom":
        return False  # port is always correct for custom
    if ms.upstream_available is None:
        return True  # not probed — can't be sure
    if ms.upstream_available is False and ms.upstream_prs:
        return True  # PR exists but not merged — track it
    return False


# ---------------------------------------------------------------------------
# Load / save (YAML round-trip)
# ---------------------------------------------------------------------------


def load_plan(path: Path) -> MigrationPlan:
    """Parse plan.yml → MigrationPlan."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    modules: dict[str, ModulePlan] = {}
    for name, raw in data.get("modules", {}).items():
        if raw is None:
            raw = {}
        origin: Optional[Origin] = None
        if raw.get("origin"):
            o = raw["origin"]
            origin = Origin(kind=o["kind"], repo=o.get("repo"), ref=o.get("ref"), pr=o.get("pr"))

        # Preserve the absent-vs-empty distinction on `tools`.
        tools: Optional[list[str]]
        if "tools" in raw:
            tools = raw["tools"] or []  # explicit [] stays []
        else:
            tools = None  # absent → inherit

        modules[name] = ModulePlan(
            name=raw.get("name", name),
            action=raw.get("action"),
            level=raw.get("level", "full"),
            strategy=raw.get("strategy"),
            origin=origin,
            depends_on=raw.get("depends_on", []),
            group=raw.get("group"),
            tools=tools,
            merge_with=raw.get("merge_with"),
            rename=raw.get("rename"),
            priority=raw.get("priority"),
            reason=raw.get("reason"),
            review=raw.get("review", False),
            pr=raw.get("pr"),
            calculated_priority=raw.get("calculated_priority"),
            descendant_count=raw.get("descendant_count", 0),
            resolved_branch=raw.get("resolved_branch"),
            resolved_tools=raw.get("resolved_tools"),
        )
    return MigrationPlan(
        version=data["version"],
        migration=data.get("migration", {}),
        defaults=data.get("defaults", {}),
        groups=data.get("groups", {}),
        modules=modules,
    )


def save_state(path: Path, state: State) -> None:
    """Serialize State → state.yml. Machine-owned, overwrite freely."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dataclasses.asdict(state)
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def load_state(path: Path) -> State:
    """Deserialize state.yml → State. Raises FileNotFoundError if missing."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    modules: dict[str, ModuleState] = {}
    for name, mod in data.get("modules", {}).items():
        modules[name] = ModuleState(
            name=mod["name"],
            origin=Origin(
                kind=mod["origin"]["kind"],
                repo=mod["origin"].get("repo"),
                ref=mod["origin"].get("ref"),
            ),
            depends_on=mod.get("depends_on", []),
            target_depends_on=mod.get("target_depends_on"),
            upstream_available=mod.get("upstream_available"),
            upstream_prs=mod.get("upstream_prs", []),
        )
    generated_at = data.get("generated_at")
    if isinstance(generated_at, str):
        generated_at = datetime.fromisoformat(generated_at)
    return State(
        version=data["version"],
        source_ref=data["source_ref"],
        from_version=data["from_version"],
        to_version=data["to_version"],
        modules=modules,
        generated_at=generated_at or datetime.now(UTC),
    )


def save_plan(path: Path, plan: MigrationPlan) -> None:
    """Serialize MigrationPlan → plan.yml.

    Human fields are written as-is. Machine fields (calculated_priority,
    descendant_count, resolved_branch, resolved_tools) are written so the
    plan is self-contained and auditable, but are always recomputed on the
    next `plan` run.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    def _module_dict(mp: ModulePlan) -> dict:
        d: dict = {"action": mp.action}

        # Human fields — only write if set.
        if mp.level and mp.level != "full":
            d["level"] = mp.level
        if mp.strategy:
            d["strategy"] = mp.strategy
        if mp.origin:
            od: dict = {"kind": mp.origin.kind}
            if mp.origin.repo:
                od["repo"] = mp.origin.repo
            if mp.origin.ref:
                od["ref"] = mp.origin.ref
            if mp.origin.pr:
                od["pr"] = mp.origin.pr
            d["origin"] = od
        if mp.depends_on:
            d["depends_on"] = mp.depends_on
        for key in ("group", "merge_with", "rename", "priority", "reason", "pr"):
            val = getattr(mp, key)
            if val is not None:
                d[key] = val
        # Preserve absent-vs-empty on tools.
        if mp.tools is not None:
            d["tools"] = mp.tools
        if mp.review:
            d["review"] = True

        # Machine fields — always written for auditability.
        if mp.calculated_priority:
            d["calculated_priority"] = mp.calculated_priority
        if mp.descendant_count:
            d["descendant_count"] = mp.descendant_count
        if mp.resolved_branch:
            d["resolved_branch"] = mp.resolved_branch
        if mp.tools is not None:
            d["resolved_tools"] = mp.resolved_tools

        return d

    out: dict = {
        "version": plan.version,
        "migration": plan.migration,
    }
    if plan.defaults:
        out["defaults"] = plan.defaults
    if plan.groups:
        out["groups"] = plan.groups
    out["modules"] = {name: _module_dict(mp) for name, mp in plan.modules.items()}

    path.write_text(
        yaml.safe_dump(out, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def get_dest_branch(migration: dict) -> str:
    """Return the destination branch name (base for all migration branches).

    Reads `dest_branch` first (explicit, preferred), then falls back to
    `target_branch` for plans that haven't been updated yet.
    Never returns a value that contains '{' — that would be a template, not a branch.
    """
    raw = migration.get("dest_branch") or migration.get("target_branch", "main")
    if "{" in raw:
        # target_branch contains a template — that's branch_template, not dest.
        # Fall back to a safe default.
        return "main"
    return raw


def get_worktree_path(migration: dict, repo_path: "Path") -> "Path":
    """Return the worktree path from the plan, or a sensible default.

    Default: sibling of repo_path, named <project>-migrate-<to_version>
    where to_version has dots replaced by dashes to avoid path confusion.
    """
    raw = migration.get("worktree_path")
    if raw:
        return Path(raw).expanduser()
    project = repo_path.name
    to = migration.get("to", "XX").replace(".", "-")  # "19.0" → "19-0"
    return repo_path.parent / f"{project}-migrate-{to}"


def get_pull_branch(migration: dict) -> str:
    """Return the pull aggregation branch name."""
    raw = migration.get("pull_branch")
    if raw:
        return raw
    to = migration.get("to", "XX")
    return f"mig/{to}/pull"
