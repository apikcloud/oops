# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: models.py — oops_engine/models.py

"""Plain analysis-result dataclasses: the output shape of module analysis.

No dependency on oops.core.config, oops.services, oops.commands, or Click —
these are pure data containers plus JSON-cache round-trip helpers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from oops_engine.compat import Any, Dict, Generic, List, Optional, T


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


@dataclass(frozen=True)
class LocStats:
    python: int = 0
    xml: int = 0
    javascript: int = 0
    docs: int = 0  # Markdown + reStructuredText combined

    @property
    def total(self) -> int:
        return self.python + self.xml + self.javascript + self.docs


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
    override_details: "list[dict]"
    missing_docstrings: int
    model_name: Optional[str] = None
    model_type: str = "model"
    inherited_methods: int = 0
    inherited_method_details: "list[dict]" = field(default_factory=list)
    ancestor_model: Optional[str] = None
    ancestor_module: Optional[str] = None
    ancestor_origin: Optional[str] = None
    root_module: Optional[str] = None  # MRO root creator (mro[-1]); original Odoo definer
    root_origin: Optional[str] = None  # raw origin of root creator
    resolved_description: Optional[str] = None
    description_inherited_from: Optional[str] = None  # module name, when inherited
    missing_description: bool = False  # new model w/o own _description


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
    method_symbols: "list[dict]" = field(default_factory=list)
    class_infos: "list[Any]" = field(default_factory=list)
    """Raw ClassInfo list (with enriched symbols) for the IR v2 machine path."""
    readme: "Optional[dict]" = None
    """README capture: {present, format, path, content} — see io.file.detect_readme."""
    domain_profile: "Optional[dict]" = None
    """Domain profile: {domains, pillars, custom_models} — see domain_profile.py."""
    method_stacks: "dict" = field(default_factory=dict)
    """Flat {(model, method_name): stack_list} for the IR method stack attachment."""
    origin: "Optional[str]" = None
    """Module KB origin (core/enterprise/oca/third_party/custom) from the KB modules table."""

    def to_cache_dict(self) -> dict:
        """Serialize to a JSON-safe dict for the analysis cache.

        `dataclasses.asdict()` alone is not enough: `module_path` is a `Path`,
        `structure.xml_analysed` is a `frozenset`, and `method_stacks` is keyed
        by `(model, method_name)` tuples — none of which `json.dumps()` accepts.
        """
        payload = asdict(self)
        payload["module_path"] = str(self.module_path)
        payload["structure"]["xml_analysed"] = sorted(self.structure.xml_analysed)
        payload["method_stacks"] = [
            {"model": model, "method": method, "stack": stack} for (model, method), stack in self.method_stacks.items()
        ]
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleSummary":
        """Reconstruct a `ModuleSummary` from `to_cache_dict()`'s output."""
        from oops_engine.inspect_module import ClassInfo, SymbolInfo  # noqa: PLC0415 — avoid a circular import

        data = dict(data)
        data["module_path"] = Path(data["module_path"])

        structure_data = dict(data["structure"])
        structure_data["xml_analysed"] = frozenset(structure_data.get("xml_analysed") or [])
        data["structure"] = StructureSummary(**structure_data)

        data["classes"] = [ClassSummary(**c) for c in data.get("classes") or []]

        if data.get("loc") is not None:
            data["loc"] = LocStats(**data["loc"])

        if data.get("views_summary") is not None:
            data["views_summary"] = ViewsSummary(**data["views_summary"])

        data["class_infos"] = [
            ClassInfo(**{**ci, "symbols": [SymbolInfo(**s) for s in ci.get("symbols") or []]})
            for ci in data.get("class_infos") or []
        ]

        data["method_stacks"] = {
            (item["model"], item["method"]): item["stack"] for item in data.get("method_stacks") or []
        }

        return cls(**data)


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
