# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: __init__.py — oops/git/__init__.py

# TODO: deprecated, to be removed in the future.

from oops.git.config import (
    get_submodule_config,
    git_config_submodule,
    git_get_regexp,
)
from oops.git.repository import (
    get_last_commit,
    list_available_addons,
    update_gitignore,
)
from oops.git.submodules import (
    rename_submodule,
    update_from,
)
from oops.git.versioning import (
    get_last_release,
    get_last_tag,
    get_next_releases,
    is_valid_semver,
)

__all__ = [
    # Submodules
    # "add_submodule",
    "rename_submodule",
    # "submodule_deinit",
    # "submodule_sync",
    # "submodule_update",
    "update_from",
    # Config
    # "extract_submodule_name",
    "get_submodule_config",
    "git_config_submodule",
    "git_get_regexp",
    # "guess_submodule_name",
    # "parse_gitmodules",
    # "parse_submodules",
    # "parse_submodules_extended",
    # Versioning
    "get_last_release",
    "get_last_tag",
    "get_next_releases",
    "is_valid_semver",
    # Repository
    "get_last_commit",
    "list_available_addons",
    "update_gitignore",
]
