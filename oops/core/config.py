# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: config.py — oops/core/config.py

import os
import typing
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

import yaml

from oops.utils.compat import List

# Sentinel for fields that must be provided via a config file (no in-code default).
_MISSING: str = object()  # type: ignore[assignment]

CONFIG_FILENAME = ".oops.yaml"
_CONFIG_PATHS = [
    Path.home() / CONFIG_FILENAME,  # global
    Path(CONFIG_FILENAME),  # local (cwd), takes precedence
]


# ---------------------------------------------------------------------------
# Nested config dataclasses
# ---------------------------------------------------------------------------


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
    source: ImageSourceConfig = field(default_factory=ImageSourceConfig)
    collections: List[str] = field(default_factory=lambda: [])
    registries: ImageRegistriesConfig = field(default_factory=ImageRegistriesConfig)
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
        ]
    )


@dataclass
class ProjectConfig:
    mandatory_files: set = field(
        default_factory=lambda: {"requirements.txt", "odoo_version.txt", "packages.txt"}
    )
    recommended_files: set = field(
        default_factory=lambda: {"README.md", "CODEOWNERS", "CHANGELOG.md", ".gitignore"}
    )
    file_packages: str = "packages.txt"
    file_requirements: str = "requirements.txt"
    file_odoo_version: str = "odoo_version.txt"
    file_migrate: str = "migrate.sh"
    pre_commit_exclude_file: str = ".pre-commit-exclusions"
    migrate_command: str = "odoo --stop-after-init --no-http -u {addons}"
    migrate_content: str = """#!/bin/bash

# Unreleased
{content}
"""


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


@dataclass
class Config:
    images: ImagesConfig = field(default_factory=ImagesConfig)
    submodules: SubmodulesConfig = field(default_factory=SubmodulesConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)

    # Internal / misc (not exposed in .oops.yaml)
    manifest_names: List[str] = field(
        default_factory=lambda: ["__manifest__.py", "__openerp__.py", "__terp__.py"]
    )
    default_timeout: int = 60
    github_api: str = "https://api.github.com"
    new_line: str = "\n"
    datetime_format: str = "%Y-%m-%d %H:%M:%S"
    check_symbol: str = "✓" if os.environ.get("LANG", "").lower().endswith(".utf-8") else "[X]"


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class ConfigurationError(Exception):
    """Raised when required configuration values are missing."""


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


def _apply(obj, data: dict) -> None:
    """Recursively merge *data* into *obj* (unknown keys are silently ignored)."""
    try:
        hints = typing.get_type_hints(type(obj))
    except Exception:
        hints = {}
    for key, value in data.items():
        if not hasattr(obj, key):
            continue
        attr = getattr(obj, key)
        if isinstance(value, dict) and is_dataclass(attr):
            _apply(attr, value)
        elif isinstance(attr, Path) and isinstance(value, (str, Path)):
            setattr(obj, key, Path(value))
        elif _is_list_of_path(hints.get(key)) and isinstance(value, list):
            setattr(obj, key, [Path(v) for v in value])
        elif isinstance(attr, set) and isinstance(value, (list, set)):
            setattr(obj, key, set(value))
        else:
            # dict fields (e.g. deprecated_repositories) are replaced wholesale, not merged.
            setattr(obj, key, value)


def load_config() -> Config:
    found = [p for p in _CONFIG_PATHS if p.exists()]
    if not found:
        raise ConfigurationError("No config file found. Create ~/.oops.yaml or .oops.yaml")
    cfg = Config()
    for path in found:
        data = yaml.safe_load(path.read_text()) or {}
        _apply(cfg, data)
    missing = _validate(cfg)
    if missing:
        raise ConfigurationError(
            f"Missing required configuration: {', '.join(missing)}. "
            f"Set them in ~/.oops.yaml or .oops.yaml"
        )
    return cfg


config = load_config()


# ---------------------------------------------------------------------------
# Manifest / rules constants (not configurable)
# ---------------------------------------------------------------------------

REPLACEMENTS = {
    "Frederic Grall": "fredericgrall",
    "Michel GUIHENEUF": "apik-mgu",
    "rth-apik": "Romathi",
    "Romain THIEUW": "Romathi",
    "Aurelien ROY": "royaurelien",
}

FORCED_KEYS = ["author", "website", "license"]

HEADERS = [
    "# pylint: disable=W0104",
    "# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).",
]

DEFAULT_VALUES = {
    "name": None,
    "summary": None,
    "category": "Technical",
    "author": "Apik",
    "maintainers": [],
    "website": "https://apik.cloud",
    "version": None,
    "license": "LGPL-3",
    "depends": [],
    "data": [],
    "demo": [],
    "assets": {},
    "installable": True,
    "application": False,
    "auto_install": False,
}
