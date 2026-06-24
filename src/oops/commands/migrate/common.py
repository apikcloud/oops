# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: common.py — src/oops/commands/migrate/common.py

# Shared helpers for the migrate workflow: artifact locations, load/save,
# and the dataclasses describing the three files (state / plan / status).
#
# Mental model (Terraform-like):
#   analyze → state.yml   machine-owned, deterministic, never hand-edited
#   plan    → plan.yml    human-owned intent, seeded from state, versioned
#   apply   → status.yml  machine-owned execution journal, re-runnable

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from oops.core.compat import Literal, Optional

if TYPE_CHECKING:
    from oops.core.models import AddonInfo

UTC = timezone.utc

# Action vocabulary — unambiguous on purpose (avoid update/upgrade).
Action = Literal["pull", "port", "drop", "keep"]
OriginKind = Literal["custom", "third-party", "oca"]


# ---------------------------------------------------------------------------
# Artifact locations
# ---------------------------------------------------------------------------
#
# .oops/migrate/ is git-ignored EXCEPT plan.yml, which is versioned.
# state.yml and status.yml are regenerable; analyze is the entry point
# after a fresh clone.

ARTIFACT_DIR = Path(".oops") / "migrate"
STATE_FILE = ARTIFACT_DIR / "state.yml"
PLAN_FILE = ARTIFACT_DIR / "plan.yml"
STATUS_FILE = ARTIFACT_DIR / "status.yml"


def artifact_path(repo_path: Path, name: Path) -> Path:
    return repo_path / name


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

    # For oca and third-party: derive repo from submodule name or website URL.
    if addon.submodule:
        return (kind, addon.submodule)

    pair = website_to_github_repo(getattr(addon, "website", None))
    if pair:
        return (kind, f"{pair[0]}/{pair[1]}")

    return (kind, None)


# ---------------------------------------------------------------------------
# Dataclasses (skeletons — fields will grow with the schema)
# ---------------------------------------------------------------------------


@dataclass
class Origin:
    """Where a module comes from. Machine field, refreshed on every plan."""

    kind: OriginKind
    repo: Optional[str] = None
    ref: Optional[str] = None


@dataclass
class ModuleState:
    """Observed facts about one module at the source ref. Machine-owned."""

    name: str
    origin: Origin
    depends_on: list[str] = field(default_factory=list)
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


@dataclass
class ModulePlan:
    """One module's intent. Human-owned except `origin` (machine-refreshed)."""

    name: str
    action: Optional[Action] = None  # must resolve to exactly one or plan refuses
    origin: Optional[Origin] = None  # machine field
    depends_on: list[str] = field(default_factory=list)
    group: Optional[str] = None
    tools: Optional[list[str]] = None  # None = inherit defaults; [] = explicit none
    merge_with: Optional[dict] = None  # {"into": "<module>"}
    rename: Optional[str] = None
    priority: Optional[str] = None
    reason: Optional[str] = None  # for drop
    review: bool = False  # set when analyze guessed and a human must confirm
    # TODO: distinguish "field absent" from "explicitly emptied" for re-seed.


@dataclass
class Plan:
    """plan.yml — the only hand-edited, versioned artifact."""

    version: int
    migration: dict  # from/to/source_ref/target_branch/strategy/branch_template
    defaults: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)
    modules: dict[str, ModulePlan] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Load / save (YAML round-trip)
# ---------------------------------------------------------------------------


def load_plan(path: Path) -> Plan:
    """Parse plan.yml → Plan."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    modules: dict[str, ModulePlan] = {}
    for name, raw in data.get("modules", {}).items():
        if raw is None:
            raw = {}
        origin: Optional[Origin] = None
        if raw.get("origin"):
            o = raw["origin"]
            origin = Origin(
                kind=o["kind"],
                repo=o.get("repo"),
                ref=o.get("ref"),
            )
        modules[name] = ModulePlan(
            name=raw.get("name", name),
            action=raw.get("action"),
            origin=origin,
            depends_on=raw.get("depends_on", []),
            group=raw.get("group"),
            tools=raw.get("tools"),
            merge_with=raw.get("merge_with"),
            rename=raw.get("rename"),
            priority=raw.get("priority"),
            reason=raw.get("reason"),
            review=raw.get("review", False),
        )
    return Plan(
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
    path.write_text(yaml.safe_dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")


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
            upstream_available=mod.get("upstream_available"),
            upstream_prs=mod.get("upstream_prs", []),
        )
    generated_at = data.get("generated_at")
    if isinstance(generated_at, str):
        from datetime import datetime
        generated_at = datetime.fromisoformat(generated_at)
    return State(
        version=data["version"],
        source_ref=data["source_ref"],
        from_version=data["from_version"],
        to_version=data["to_version"],
        modules=modules,
        generated_at=generated_at or datetime.now(UTC),
    )


def save_plan(path: Path, plan: Plan) -> None:
    """Serialize Plan → plan.yml (PyYAML; YAML comments not preserved)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def _module_dict(mp: ModulePlan) -> dict:
        d: dict = {"action": mp.action}
        if mp.origin:
            od: dict = {"kind": mp.origin.kind}
            if mp.origin.repo:
                od["repo"] = mp.origin.repo
            if mp.origin.ref:
                od["ref"] = mp.origin.ref
            d["origin"] = od
        if mp.depends_on:
            d["depends_on"] = mp.depends_on
        for key in ("group", "tools", "merge_with", "rename", "priority", "reason"):
            val = getattr(mp, key)
            if val is not None:
                d[key] = val
        if mp.review:
            d["review"] = True
        return d

    data: dict = {
        "version": plan.version,
        "migration": plan.migration,
    }
    if plan.defaults:
        data["defaults"] = plan.defaults
    if plan.groups:
        data["groups"] = plan.groups
    data["modules"] = {name: _module_dict(mp) for name, mp in plan.modules.items()}

    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _guess_action(ms: ModuleState) -> Action:
    """Guess the migration action from a module's observed state."""
    if ms.origin.kind == "custom":
        return "port"
    if ms.upstream_available is True:
        return "pull"
    return "port"


def _needs_review(ms: ModuleState, action: Action) -> bool:
    """True when the guessed action is uncertain and a human must confirm."""
    if ms.origin.kind == "custom":
        return False
    if ms.upstream_available is None:
        return True
    if ms.upstream_available is False and ms.upstream_prs:
        return True
    return False
