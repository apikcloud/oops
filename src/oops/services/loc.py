# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: loc.py — oops/services/loc.py

"""Back-compat re-exports for per-addon LOC statistics.

The implementation lives in `oops_engine.loc` (portable, no config/git
dependency); this module keeps existing `oops.services.loc` import sites
working unchanged.
"""

from __future__ import annotations

from oops_engine.loc import (  # noqa: F401 — back-compat re-export
    _has_cloc,
    get_addon_loc,
    get_addon_loc_cached,
)
from oops_engine.models import LocStats  # noqa: F401 — back-compat re-export
