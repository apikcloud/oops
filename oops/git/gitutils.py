"""
DEPRECATED: This module is kept for backward compatibility only.

All functionality has been refactored into specialized modules:
- oops.git.core: Basic git operations (commit, add, reset, get_root_path)
- oops.git.submodules: Submodule management
- oops.git.config: Git configuration and .gitmodules parsing
- oops.git.versioning: Tags, releases, semantic versioning
- oops.git.repository: Repository helpers

Please import directly from oops.git instead:
    from oops.git import commit, load_repo, parse_gitmodules

This file will be removed in a future version.
"""

import warnings

# Re-export everything from the new modules for backward compatibility
from oops.git import *  # noqa: F401, F403

warnings.warn(
    "oops.git.gitutils is deprecated. Import from oops.git instead.",
    DeprecationWarning,
    stacklevel=2,
)
