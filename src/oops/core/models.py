# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: models.py — oops/core/models.py

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from oops.core.compat import Any, Dict, Generic, List, Literal, Optional, T
from oops.utils.helpers import date_from_string
from oops.utils.render import format_datetime

if TYPE_CHECKING:
    from oops.services.loc import LocStats

UTC = timezone.utc

# Semantic versioning pattern: v1.2.3
SEMVER_PATTERN = re.compile(r"^v(?P<x>0|[1-9]\d*)\.(?P<y>0|[1-9]\d*)\.(?P<z>0|[1-9]\d*)$")


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
    # Git-state fields — None until enrich_addon() is called
    submodule: Optional[str] = None  # submodule name (e.g. "OCA/server-tools"), "" if not in one
    branch: Optional[str] = None  # upstream branch tracked by the submodule
    pull_request: Optional[bool] = None
    classification: Optional[str] = None  # "custom" | "oca" | "third-party"

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
        )


@dataclass
class ClassSummary:
    class_name: str
    is_new_model: bool
    inherit: "list[str]"
    fields_total: int
    fields_base: int
    fields_new: int
    fields_inherited: int
    fields_by_type: "dict[str, int]"
    methods_total: int
    methods_by_section: "dict[str, int]"
    overrides: int
    override_details: "list[dict[str, str]]"
    missing_docstrings: int
    model_name: Optional[str] = None
    model_type: str = "model"
    inherited_methods: int = 0
    inherited_method_details: "list[dict[str, str]]" = field(default_factory=list)
    ancestor_model: Optional[str] = None
    ancestor_module: Optional[str] = None
    ancestor_origin: Optional[str] = None


@dataclass
class ViewsSummary:
    primary_by_type: "dict[str, int]"
    extensions: int
    extensions_by_type: "dict[str, int]"
    extensions_upstream: int
    actions: int
    menus: int
    unresolved: int
    view_list: "list[dict]" = field(default_factory=list)


@dataclass
class StructureSummary:
    data: "dict[str, dict[str, int]]"
    demo: "dict[str, dict[str, int]]"
    controllers_py: int
    wizard_py: int
    report_py: int
    static_by_ext: "dict[str, int]"
    xml_analysed: "frozenset[str]" = field(default_factory=frozenset)


@dataclass
class ModuleSummary:
    module_name: str
    module_path: Path
    manifest: dict
    classes: "list[ClassSummary]"
    structure: StructureSummary
    loc: "Optional[LocStats]" = None
    loc_pct: float = 0.0
    views_summary: "Optional[ViewsSummary]" = None


@dataclass
class Result(Generic[T]):
    data: "Optional[T]" = None
    messages: "list[str]" = field(default_factory=list)
    warnings: "list[str]" = field(default_factory=list)
    errors: "list[str]" = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

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
class Rows:
    title: str = "Results"
    columns: list[tuple[str, str, str]] = field(default_factory=list)
    rows: list[Any] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)


@dataclass
class ChangelogSection:
    version: str
    date: str
    entries: Dict[str, List[str]] = field(default_factory=dict)


class ReleaseType(str, Enum):
    MAJOR = "major"
    MINOR = "minor"
    FIX = "fix"
    UNKNOWN = "unknown"


@dataclass
class Release:
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
            d.pop("kind", None)
            d.pop("highlight", None)
        return d


@dataclass
class StatGroup:
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
class SubmoduleInfo:
    name: str
    url: str
    branch: Optional[str]
    pull_request: bool
    last_commit: Optional[CommitInfo]

    def to_dict(self) -> dict:
        return asdict(self)
