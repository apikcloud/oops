# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: models.py — oops/core/models.py

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from oops.utils.compat import Generic, Optional, T
from oops.utils.helpers import date_from_string
from oops.utils.render import format_datetime

UTC = timezone.utc


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
    def from_raw_dict(cls, vals: dict):
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
    maintainers: "list[str]"
    summary: str
    external_dependencies: "dict[str, list[str]]"
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
    def from_path(cls, path: Path, root_path: Path, manifest: dict) -> "AddonInfo":
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


@dataclass
class StructureSummary:
    data: "dict[str, dict[str, int]]"
    demo: "dict[str, dict[str, int]]"
    controllers_py: int
    wizard_py: int
    report_py: int
    static_by_ext: "dict[str, int]"


@dataclass
class ModuleSummary:
    module_name: str
    module_path: Path
    manifest: dict
    classes: "list[ClassSummary]"
    structure: StructureSummary
    warnings: "list[str]" = field(default_factory=list)


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
