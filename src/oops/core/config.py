# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: config.py — oops/core/config.py

import logging
import os
import typing
import warnings
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Final, Union

import click
import yaml
from oops.core.exceptions import ConfigurationError
from oops.core.paths import CONFIG_PATHS as _CONFIG_PATHS
from oops.utils.compat import List, Optional

logger = logging.getLogger(__name__)

# Sentinel for fields that must be provided via a config file (no in-code default).
_MISSING: Final = object()

_SUPPORTED_VERSIONS: Final = {1}

DOCS_URL = "https://apikcloud.github.io/oops/"


# ---------------------------------------------------------------------------
# Nested config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ManifestConfig:
    author: str = _MISSING  # type: ignore[assignment]
    odoo_version: Optional[str] = None  # e.g. "19.0" — enforced in version check
    edition: str = "enterprise"  # "community" | "enterprise"
    version_bump_strategy: str = "off"  # "off" | "strict" | "trunk"
    allowed_maintainers: List[str] = field(default_factory=lambda: [])
    required_keys: List[str] = field(
        default_factory=lambda: [
            "name",
            "version",
            "summary",
            "website",
            "author",
            "maintainers",
            "depends",
            "data",
            "license",
            "auto_install",
            "installable",
        ]
    )
    key_order: List[str] = field(
        default_factory=lambda: [
            "name",
            "summary",
            "version",
            "category",
            "author",
            "maintainers",
            "website",
            "depends",
            "data",
            "assets",
            "demo",
            "application",
            "auto_install",
            "installable",
            "license",
            "pre_init_hook",
            "post_init_hook",
            "uninstall_hook",
            "post_load",
        ]
    )


@dataclass
class SyncConfig:
    remote_url: Optional[str] = None
    branch: Optional[str] = None
    files: List[str] = field(default_factory=lambda: [])


@dataclass
class ImageSourceConfig:
    repository: str = _MISSING  # type: ignore[assignment]
    file: str = _MISSING  # type: ignore[assignment]

    @property
    def url(self) -> str:
        return f"https://raw.githubusercontent.com/{self.repository}/refs/heads/main/{self.file}"


@dataclass
class ImageRegistriesConfig:
    recommended: List[str] = field(default_factory=lambda: [])
    deprecated: List[str] = field(default_factory=lambda: [])
    warn: List[str] = field(default_factory=lambda: [])


@dataclass
class ImagesConfig:
    source: ImageSourceConfig = field(default_factory=lambda: ImageSourceConfig())
    collections: List[str] = field(default_factory=lambda: [])
    registries: ImageRegistriesConfig = field(default_factory=lambda: ImageRegistriesConfig())
    release_warn_age_days: int = 30


@dataclass
class SubmodulesConfig:
    current_path: Path = field(default_factory=lambda: Path(".third-party"))
    old_paths: List[Path] = field(default_factory=lambda: [Path("third-party")])
    force_scheme: str = "ssh"
    deprecated_repositories: dict = field(default_factory=lambda: {})
    checks: List[str] = field(
        default_factory=lambda: [
            "check_path",
            "check_branch",
            "check_symlink",
            "check_url_scheme",
            "check_deprecated_repo",
            "check_broken_symlink",
            "check_pr",
        ]
    )


@dataclass
class OdooConfig:
    sources_dir: Optional[Path] = None
    community_url: str = "git@github.com:odoo/odoo.git"
    enterprise_url: str = "git@github.com:odoo/enterprise.git"


@dataclass
class PrecommitConfig:
    default_exclusions: List[str] = field(
        default_factory=lambda: [
            r"^setup/|/static/description/index\.html$",
            ".svg$|/tests/([^/]+/)?cassettes/|^.copier-answers.yml$|^.github/|^eslint.config.cjs|^prettier.config.cjs",
            r"^README\.md$",
            "/static/(src/)?lib/",
            r"^docs/_templates/.*\.html$",
            r"readme/.*\.(rst|md)$",
            "/build/|/dist/",
            "/tests/samples/.*",
            "(LICENSE.*|COPYING.*)",
            ".third-party/",
            "third-party/",
        ]
    )
    file_precommit: str = ".pre-commit-config.yaml"


@dataclass
class ProjectConfig:
    mandatory_files: set = field(default_factory=lambda: {"requirements.txt", "odoo_version.txt", "packages.txt"})
    recommended_files: set = field(default_factory=lambda: {"README.md", "CODEOWNERS", "CHANGELOG.md", ".gitignore"})
    file_packages: str = "packages.txt"
    file_requirements: str = "requirements.txt"
    file_odoo_version: str = "odoo_version.txt"
    file_migrate: str = "migrate.sh"
    readme_file: str = "README.md"


@dataclass
class StatsConfig:
    enabled: bool = False
    endpoint: Optional[str] = None


@dataclass
class GithubConfig:
    owner: Optional[str] = None  # GitHub org or user that will own the new repo
    team: Optional[str] = None  # GitHub team granted push access after repo creation
    template: Optional[str] = None  # "owner/repo" of the GitHub template repository
    prefix: Optional[str] = None  # prepended to every slug, e.g. "client" → "client-my-project"
    visibility: str = "private"  # default visibility for new repositories
    action_repo: Optional[str] = None  # "owner/repo" of the repo holding the post-create workflow
    action_workflow: Optional[str] = None  # workflow filename, e.g. "setup.yml"
    action_ref: str = "main"  # branch/tag to dispatch the workflow on
    action_inputs: dict = field(default_factory=dict)  # extra static inputs passed to the workflow


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


@dataclass
class Config:
    version: float = _MISSING  # type: ignore[assignment]
    images: ImagesConfig = field(default_factory=ImagesConfig)
    submodules: SubmodulesConfig = field(default_factory=SubmodulesConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    manifest: ManifestConfig = field(default_factory=ManifestConfig)  # type: ignore[call-arg]
    odoo: OdooConfig = field(default_factory=OdooConfig)
    precommit: PrecommitConfig = field(default_factory=PrecommitConfig)
    github: GithubConfig = field(default_factory=GithubConfig)
    stats: StatsConfig = field(default_factory=StatsConfig)

    # Internal / misc (not exposed in .oops.yaml)
    manifest_names: List[str] = field(default_factory=lambda: ["__manifest__.py", "__openerp__.py", "__terp__.py"])
    default_timeout: int = 60
    github_api: str = "https://api.github.com"
    new_line: str = "\n"
    datetime_format: str = "%Y-%m-%d %H:%M:%S"
    check_symbol: str = "✓" if os.environ.get("LANG", "").lower().endswith(".utf-8") else "[X]"
    pull_request_dir: str = "PRs"


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


def _validate(obj, path: str = "") -> List[str]:
    """Return dotted paths of required fields not yet populated."""
    missing = []
    for f in fields(obj):
        value = getattr(obj, f.name)
        key = f"{path}.{f.name}" if path else f.name
        if value is _MISSING:
            missing.append(key)
        elif is_dataclass(value):
            missing.extend(_validate(value, key))
    return missing


def _is_list_of_path(hint: object) -> bool:
    return getattr(hint, "__origin__", None) is list and getattr(hint, "__args__", ()) == (Path,)


def _is_path_hint(hint: object) -> bool:
    """Return True if *hint* is Path or Optional[Path]."""
    if hint is Path:
        return True
    if getattr(hint, "__origin__", None) is Union:
        return Path in getattr(hint, "__args__", ())
    return False


def _apply(obj, data: dict, path: str = "") -> None:
    """Recursively merge *data* into *obj*.

    Unknown keys produce a warning rather than being silently ignored.
    Dict and set fields are replaced wholesale (not merged) — intentional,
    so that a project-level config can fully override a global default.
    """
    try:
        hints = typing.get_type_hints(type(obj))
    except Exception:
        hints = {}

    for key, value in data.items():
        full_key = f"{path}.{key}" if path else key
        if not hasattr(obj, key):
            warnings.warn(
                f"Unknown config key ignored: '{full_key}'",
                UserWarning,
                stacklevel=2,
            )
            continue
        attr = getattr(obj, key)
        if isinstance(value, dict) and is_dataclass(attr):
            _apply(attr, value, full_key)
        elif _is_path_hint(hints.get(key)) and isinstance(value, (str, Path)):
            setattr(obj, key, Path(value).expanduser())
        elif _is_list_of_path(hints.get(key)) and isinstance(value, list):
            setattr(obj, key, [Path(v) for v in value])
        elif isinstance(attr, set) and isinstance(value, (list, set)):
            setattr(obj, key, set(value))
        else:
            setattr(obj, key, value)


def _check_version(data: dict, path: Path) -> None:
    """Validate the 'version' key from a config file."""
    version = data.get("version")
    if version is None:
        warnings.warn(
            f"{path}: no 'version' key found, assuming v1",
            UserWarning,
            stacklevel=1,
        )
    elif version not in _SUPPORTED_VERSIONS:
        raise ConfigurationError(
            f"{path}: unsupported config version {version!r} (supported: {sorted(_SUPPORTED_VERSIONS)})"
        )


def load_config() -> Config:
    found = [p for p in _CONFIG_PATHS if p.exists()]
    if not found:
        ctx = click.get_current_context(silent=True)
        if ctx is not None and ctx.resilient_parsing:
            return Config()

        ConfigurationError.__suppress_context__ = True
        raise ConfigurationError("No config file found. Create ~/.oops.yaml or .oops.yaml") from None

    cfg = Config()
    for path in found:
        logger.debug("Loading config from %s", path)
        data = yaml.safe_load(path.read_text()) or {}
        _check_version(data, path)
        _apply(cfg, data)

    missing = _validate(cfg)
    if missing:
        grouped: dict[str, list[str]] = {}
        for m in missing:
            root = m.split(".")[0]
            grouped.setdefault(root, []).append(m)
        lines = "\n".join(f"  [{section}]: {', '.join(keys)}" for section, keys in grouped.items())
        raise ConfigurationError(f"Missing required configuration:\n{lines}\nSet them in ~/.oops.yaml or .oops.yaml")

    logger.debug("Config loaded successfully")
    return cfg


class _LazyConfig:
    _cfg: "Config | None" = None

    def _load(self) -> Config:
        if type(self)._cfg is None:
            type(self)._cfg = load_config()
        return type(self)._cfg  # type: ignore[return-value]

    def __getattr__(self, name: str):
        return getattr(self._load(), name)

    def __setattr__(self, name: str, value) -> None:
        if name == "_cfg":
            object.__setattr__(self, name, value)
        else:
            setattr(self._load(), name, value)


config: Config = _LazyConfig()  # type: ignore[assignment]
