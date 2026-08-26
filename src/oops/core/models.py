# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: models.py — oops/core/models.py

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path

from oops.core.compat import TYPE_CHECKING, Any, Dict, Generic, List, Literal, Optional, Protocol, T
from oops.utils.helpers import date_from_string

if TYPE_CHECKING:
    from oops_engine.models import LocStats

UTC = timezone.utc

# Semantic versioning pattern: v1.2.3
SEMVER_PATTERN = re.compile(r"^v(?P<x>0|[1-9]\d*)\.(?P<y>0|[1-9]\d*)\.(?P<z>0|[1-9]\d*)$")

# Kinds that are NOT executed when iterating a plan.
_INACTIVE_KINDS = frozenset({"nothing to do", "skip", "skipped", "step", "blocked"})


@dataclass
class ImageInfo:
    image: str
    registry: str
    repository: str
    major_version: float
    release: Optional[date]
    enterprise: bool
    legacy: bool = False
    delta: int = 0  # days since release, to be filled later
    collection: Optional[str] = None  # to be filled later

    @property
    def source(self) -> str:
        return f"{self.registry}/{self.repository}"

    @property
    def edition(self) -> str:
        return "enterprise" if self.enterprise else "community"

    @property
    def age(self) -> Optional[int]:
        if self.release:
            return (date.today() - self.release).days
        return None

    @classmethod
    def from_raw_dict(cls, vals: Dict):
        return cls(
            **{
                "image": vals["image"],
                "registry": vals["org"],
                "repository": vals["repo"],
                "major_version": float(vals["version"]),
                "release": date_from_string(vals["release"]),
                "enterprise": vals["edition"] == "enterprise",
                "collection": vals.get("collection"),
            }
        )


@dataclass
class CommitInfo:
    author: str
    date: datetime
    email: str
    message: str
    sha: str

    @property
    def age(self) -> int:
        """
        Returns the integer number of days since the commit date (truncates partial days).
        """
        return (datetime.today().date() - self.date.date()).days

    @classmethod
    def from_string(cls, output: str, sep: str = ";") -> "CommitInfo":
        """ "--pretty=format:%h;%an;%ae;%ad;%s"
        1. sha
        2. author name
        3. author email
        4. date (ISO 8601 format)
        5. commit message
        """
        sha, author, email, date_str, message = output.split(sep, 4)
        commit_date = datetime.fromisoformat(date_str)
        return cls(
            sha=sha,
            author=author,
            email=email,
            date=commit_date,
            message=message,
        )

    def __str__(self) -> str:
        from oops.utils.render import format_datetime  # noqa: PLC0415 — keep config out of this module's import graph

        return f"{self.message} by {self.author} on {format_datetime(self.date)} ({self.sha})"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        return d


@dataclass
class WorkflowRunInfo:
    actor: str
    branch: str
    conclusion: str
    date: datetime
    event: str
    name: str
    sha: str
    status: str
    url: str

    @property
    def age(self) -> int:
        """
        Returns the integer number of days since the commit date (truncates partial days).
        """
        return (datetime.today().date() - self.date.date()).days

    @classmethod
    def from_dict(cls, vals: dict) -> "WorkflowRunInfo":
        # ISO8601 -> datetime (handles trailing 'Z')
        created = datetime.fromisoformat(vals["created_at"].replace("Z", "+00:00")).astimezone(UTC)

        return cls(
            **{
                "name": vals["name"],
                "event": vals["event"],
                "status": vals["status"],
                "conclusion": vals["conclusion"],
                "sha": vals["head_sha"],
                "branch": vals["head_branch"],
                "date": created,
                "url": vals["url"],
                "actor": vals["actor"]["login"],
            }
        )

    def __str__(self) -> str:
        return (
            f"{self.name} triggered by {self.event} on {self.branch} by {self.actor} ({self.status}/{self.conclusion})"  # noqa: E501
        )


@dataclass
class AddonInfo:
    # Manifest + filesystem fields — always populated by from_path()
    path: str
    rel_path: str
    technical_name: str
    symlink: bool
    root: bool
    version: str
    author: str
    maintainers: "List[str]"
    depends: "List[str]"
    summary: str
    external_dependencies: "Dict[str, List[str]]"
    installable: bool
    website: Optional[str] = None
    # Git-state fields — None until enrich_addon() is called
    submodule: Optional[str] = None  # submodule name (e.g. "OCA/server-tools"), "" if not in one
    branch: Optional[str] = None  # upstream branch tracked by the submodule
    pull_request: Optional[bool] = None
    classification: Optional[str] = None  # "custom" | "oca" | "third-party"

    # Line of code
    loc: "Optional[LocStats]" = None
    loc_pct: float = 0.0

    @property
    def symlinked(self) -> bool:
        return self.symlink and self.root

    @property
    def location(self) -> str:
        if self.symlinked:
            return "active"
        elif self.root:
            return "local"
        else:
            return "inactive"

    @classmethod
    def from_path(cls, path: Path, root_path: Path, manifest: Dict) -> "AddonInfo":
        symlink = path.is_symlink()
        root = path.parent == root_path

        if symlink:
            path = path.resolve()
        rel_path = str(path.relative_to(root_path).parent)
        rel_path = "" if rel_path == "." else rel_path

        return cls(
            path=str(path),
            technical_name=path.name,
            symlink=symlink,
            root=root,
            rel_path=rel_path,
            version=manifest.get("version", "unknown"),
            author=manifest.get("author", "unknown"),
            maintainers=manifest.get("maintainers", []),
            depends=manifest.get("depends", []),
            summary=manifest.get("summary", ""),
            external_dependencies=manifest.get("external_dependencies", {}),
            installable=manifest.get("installable", True),
            website=manifest.get("website"),
        )


class HasStatus(Protocol):
    @property
    def ok(self) -> bool: ...
    @property
    def warnings(self) -> list[str]: ...
    @property
    def errors(self) -> list[str]: ...


@dataclass
class Result(Generic[T]):
    data: "Optional[T]" = None
    messages: "list[str]" = field(default_factory=list)
    warnings: "list[str]" = field(default_factory=list)
    errors: "list[str]" = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def unwrap(self) -> T:
        if self.data is None:
            raise ValueError("Result has no data")
        return self.data

    def add_message(self, message: str) -> None:
        self.messages.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def merge(self, other: "Result") -> "Result[T]":
        self.messages.extend(other.messages)
        self.warnings.extend(other.warnings)
        self.errors.extend(other.errors)
        return self


@dataclass
class ResultCollection(Generic[T]):
    """Aggregates multiple Result[T] plus collection-level warnings/errors."""

    title: str
    items: list[Result[T]] = field(default_factory=list)
    messages: "list[str]" = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and all(item.ok for item in self.items)

    @property
    def unwrap(self) -> "list[Result[T]]":
        if self.items is None:
            raise ValueError("ResultCollection has no results")
        return self.items

    def add(self, result: Result[T]) -> None:
        self.items.append(result)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def merge(self, other: Result) -> "ResultCollection[T]":
        """Merge a global Result (warnings/errors) into the collection."""
        self.messages.extend(other.messages)
        self.warnings.extend(other.warnings)
        self.errors.extend(other.errors)

        return self

    def aggregate(self):
        for item in self.items:
            self.messages.extend(item.messages)
            self.warnings.extend(item.warnings)
            self.errors.extend(item.errors)

        self.messages.sort()
        self.warnings.sort()
        self.errors.sort()

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)


@dataclass
class Rows:
    rows: list[Any]
    title: str = "Results"
    columns: list[Any] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)


@dataclass
class ChangelogSection:
    """One version block parsed from a Keep-a-Changelog formatted file."""

    version: str
    date: str
    entries: Dict[str, List[str]] = field(default_factory=dict)


class ReleaseType(str, Enum):
    """Semantic classification of a release based on semver patch/minor/major fields."""

    MAJOR = "major"
    MINOR = "minor"
    FIX = "fix"
    UNKNOWN = "unknown"


@dataclass
class Release:
    """A git-tagged release with commit statistics and optional changelog data."""

    name: str
    date: date
    author: str
    commits: int
    changelog: "Optional[ChangelogSection]" = None

    @property
    def release_type(self) -> ReleaseType:
        m = SEMVER_PATTERN.match(self.name)
        if not m:
            return ReleaseType.UNKNOWN
        if m.group("z") != "0":
            return ReleaseType.FIX
        if m.group("y") != "0":
            return ReleaseType.MINOR
        return ReleaseType.MAJOR

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        d["release_type"] = self.release_type.value
        return d


StatKind = Literal["count", "date", "text", "boolean"]


@dataclass
class Stat:
    """A single named metric value for display in a stats panel."""

    name: str
    label: str
    value: Any
    kind: StatKind = "count"
    highlight: bool = False

    def to_dict(self, summary: bool = False) -> dict:
        """Serialize.

        When `summary=True`, drop fields irrelevant to a compact payload
        (kind, highlight) — useful for the machine summary view.
        """
        d = asdict(self)
        if summary:
            d.pop("label", None)
            d.pop("kind", None)
            d.pop("highlight", None)
        return d


@dataclass
class StatGroup:
    """A labelled collection of :class:`Stat` values rendered together as a panel."""

    name: str
    label: str
    values: list[Stat] = field(default_factory=list)

    def to_dict(self, summary: bool = False) -> dict:
        return {
            "kind": "stats",
            "label": self.label,
            "values": [s.to_dict(summary=summary) for s in self.values],
        }

    def get(self, name: str) -> Stat | None:
        """Find a stat by name. Useful in templates."""
        return next((s for s in self.values if s.name == name), None)


@dataclass
class PullRequest:
    upstream: str
    number: int
    state: str
    title: str
    url: str
    head: str
    base: str
    head_repo_url: Optional[str] = None
    head_ref: Optional[str] = None
    head_owner: Optional[str] = None
    head_repo: Optional[str] = None
    author: Optional[str] = None

    @classmethod
    def from_dict(cls, upstream: str, data: dict) -> "PullRequest":
        head = data["head"]
        head_repo = head.get("repo") or {}
        user = data.get("user") or {}

        # labels = ", ".join([item["name"] for item in data.get("labels", []) if item["default"]])
        state = "merged" if bool(data["merged_at"]) else data["state"]

        return cls(
            upstream=upstream,
            number=data["number"],
            state=state,
            title=data["title"],
            url=data["html_url"],
            head=head["label"],
            base=data["base"]["label"],
            head_repo_url=head_repo.get("clone_url"),
            head_ref=head.get("ref"),
            head_owner=(head_repo.get("owner") or {}).get("login"),
            head_repo=head_repo.get("name"),
            author=user.get("login"),
        )


@dataclass
class SubmoduleInfo:
    name: str
    url: str
    branch: Optional[str]
    pull_request: bool
    last_commit: Optional[CommitInfo]
    pull_requests: Optional[list[PullRequest]] = None

    @property
    def resolved_pr(self) -> Optional[PullRequest]:
        return self.pull_requests[0] if self.pull_requests else None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlanAction:
    """A single planned mutation, before execution.

    Attributes:
        label: Identifier of the target (e.g. the submodule name).
        new: The new value the action will produce (new name/path), or None.
        kind: Lifecycle marker — "available", "selected", "skipped",
            "nothing to do", or any command-specific verb. Drives both
            filtering (via Plan.actionable) and presentation (via the presenter).
        detail: Optional secondary string for display (e.g. a new path).
        data: Free-form payload the `apply` callback needs at execution time.
    """

    label: str
    new: "Optional[str]" = None
    kind: str = "available"
    detail: str = ""
    data: dict = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.kind not in _INACTIVE_KINDS


@dataclass
class Plan:
    """A set of planned actions, before execution.

    The plan is built as pure data (no colours, no I/O). Selection,
    restriction and presentation are applied to it afterwards.
    """

    title: str
    actions: "list[PlanAction]" = field(default_factory=list)

    def __iter__(self):
        return iter(self.actions)

    def __len__(self) -> int:
        return len(self.actions)

    @property
    def actionable(self) -> "list[PlanAction]":
        """Actions that will actually be executed."""
        return [a for a in self.actions if a.active]

    @property
    def count(self) -> Counter:
        """Counter of action kinds, for summary metrics."""
        return Counter(a.kind for a in self.actions)

    def restrict_to(self, names: "set[str]") -> None:
        """Mark available actions not in `names` as skipped.

        Used for non-interactive narrowing via CLI arguments.
        """
        for action in self.actions:
            if action.kind == "available" and action.label not in names:
                action.kind = "skipped"

    def apply_selection(self, selected: "set[str]", verb: str = "selected") -> None:
        """Mark available actions: `verb` if selected, else skipped."""
        for action in self.actions:
            if action.kind != "available":
                continue
            action.kind = verb if action.label in selected else "skipped"
