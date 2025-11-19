import os
from dataclasses import dataclass, field

import black

from oops.utils.compat import List

BLACK_MODE = black.FileMode()


@dataclass
class Config:
    # Submodule
    new_submodule_path: str = ".third-party"
    old_submodule_path: str = "third-party"

    # Manifest
    manifest_names: List[str] = field(
        default_factory=lambda: ["__manifest__.py", "__openerp__.py", "__terp__.py"]
    )

    # Docker images
    repo_docker_images: str = "apikcloud/images"
    repo_docker_file: str = "tags.json"
    docker_collections: List[str] = field(default_factory=lambda: ["production", "ofleet"])
    docker_recommended_registries: List[str] = field(default_factory=lambda: ["apik"])
    docker_deprecated_registries: List[str] = field(default_factory=lambda: ["ofleet", "loginline"])
    docker_warn_registries: List[str] = field(default_factory=lambda: ["odoo"])
    release_warn_age_days: int = 30

    # Project files
    project_mandatory_files: set = field(
        default_factory=lambda: {"requirements.txt", "odoo_version.txt", "packages.txt"}
    )
    project_recommended_files: set = field(
        default_factory=lambda: {"README.md", "CODEOWNERS", "CHANGELOG.md", ".gitignore"}
    )
    project_file_packages: str = "packages.txt"
    project_file_requirements: str = "requirements.txt"
    project_file_odoo_version: str = "odoo_version.txt"

    # Network
    default_timeout: int = 60
    github_api: str = "https://api.github.com"

    # Misc
    new_line: str = "\n"
    datetime_format: str = "%Y-%m-%d %H:%M:%S"
    check_symbol: str = "✓" if os.environ.get("LANG", "").lower().endswith(".utf-8") else "[X]"
    pre_commit_exclude_file: str = ".pre-commit-exclusions"

    @property
    def odoo_images_url(self) -> str:
        return f"https://raw.githubusercontent.com/{self.repo_docker_images}/refs/heads/main/{self.repo_docker_file}"


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


config = Config()
