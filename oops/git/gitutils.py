# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: gitutils.py — oops/git/gitutils.py

# TODO: deprecated, to be removed in the future.

import warnings

# Re-export everything from the new modules for backward compatibility
from oops.git import *  # noqa: F401, F403

warnings.warn(
    "oops.git.gitutils is deprecated. Import from oops.git instead.",
    DeprecationWarning,
    stacklevel=2,
)
