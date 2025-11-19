import os

import black

NEW_SUBMODULES_PATH = ".third-party"
OLD_SUBMODULES_PATH = "third-party"

GITHUB_API = "https://api.github.com"

MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py", "__terp__.py")

BLACK_MODE = black.FileMode()
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


REPO_DOCKER_IMAGES = "apikcloud/images"
REPO_DOCKER_FILE = "tags.json"
ODOO_IMAGES_URL = (
    f"https://raw.githubusercontent.com/{REPO_DOCKER_IMAGES}/refs/heads/main/{REPO_DOCKER_FILE}"
)

DEFAULT_TIMEOUT = 60
DOCKER_COLLECTIONS = ["production", "ofleet"]
DOCKER_RECOMMENDED_REGISTRIES = ["apik"]
DOCKER_DEPRECATED_REGISTRIES = ["ofleet", "loginline"]
DOCKER_WARN_REGISTRIES = ["odoo"]

PROJECT_MANDATORY_FILES = {"requirements.txt", "odoo_version.txt", "packages.txt"}
PROJECT_RECOMMENDED_FILES = {"README.md", "CODEOWNERS", "CHANGELOG.md", ".gitignore"}

PROJECT_FILE_PACKAGES = "packages.txt"
PROJECT_FILE_REQUIREMENTS = "requirements.txt"
PROJECT_FILE_ODOO_VERSION = "odoo_version.txt"

NEW_LINE = "\n"

PRE_COMMIT_EXCLUDE_FILE = ".pre-commit-exclusions"


RELEASE_WARN_AGE_DAYS = 30


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


CHECK_SYMBOL = "✓" if os.environ.get("LANG", "").lower().endswith(".utf-8") else "[X]"
