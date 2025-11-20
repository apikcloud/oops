"""Git operations module - Refactored into specialized submodules.

This module provides a unified interface to all git operations, organized into:
- core: Basic git commands (commit, add, reset, etc.)
- submodules: Submodule management (add, update, sync, etc.)
- config: Git configuration and .gitmodules parsing
- versioning: Tags, releases, and semantic versioning
- repository: Repository-level helpers (load_repo, remote_url, etc.)

For backward compatibility, all functions are re-exported at this level.
"""

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
