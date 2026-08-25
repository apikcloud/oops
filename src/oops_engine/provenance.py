# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: provenance.py — oops_engine/provenance.py

"""Single provenance vocabulary for the analyze IR (schema_version 2).

Collapses the three legacy vocabularies — addon ``classification`` (``"oca"``),
model ``ancestor_origin`` (``"odoo"``), view ``origin`` (``"third-party"`` /
``"custom"``) — and the KB tier labels into one controlled enum.

``origin ∈ { core, enterprise, oca, third_party, custom }``
"""

from __future__ import annotations

from oops.core.compat import Optional

# origin ∈ { core, enterprise, oca, third_party, custom }
ORIGIN_CORE = "core"
ORIGIN_ENTERPRISE = "enterprise"
ORIGIN_OCA = "oca"
ORIGIN_THIRD_PARTY = "third_party"
ORIGIN_CUSTOM = "custom"

ORIGINS = frozenset(
    {
        ORIGIN_CORE,
        ORIGIN_ENTERPRISE,
        ORIGIN_OCA,
        ORIGIN_THIRD_PARTY,
        ORIGIN_CUSTOM,
    }
)

# Raw KB/tier label → v2 enum.
_RAW_ORIGIN_MAP = {
    "odoo": ORIGIN_CORE,
    "odoo_core": ORIGIN_CORE,   # community/odoo/addons tier
    "community": ORIGIN_CORE,
    "enterprise": ORIGIN_ENTERPRISE,
    "themes": ORIGIN_CORE,
    "third-party": ORIGIN_THIRD_PARTY,
    "third_party": ORIGIN_THIRD_PARTY,
    "oca": ORIGIN_OCA,
    "custom": ORIGIN_CUSTOM,
    # view-layer labels seen in the KB
    "project": ORIGIN_CUSTOM,
}


def normalize_origin(raw: Optional[str]) -> Optional[str]:
    """Map a raw KB/tier origin label to the v2 ``origin`` enum.

    Args:
        raw: A legacy origin/tier label, ``None`` or ``""``.

    Returns:
        ``None`` ("not enriched") and ``""`` ("enriched, no origin") are
        preserved unchanged. Any known label maps to its enum member; unknown
        non-empty labels fall back to ``third_party``.
    """
    if raw is None or raw == "":
        return raw  # preserve None ("not enriched") and "" ("enriched, no origin")
    return _RAW_ORIGIN_MAP.get(raw, ORIGIN_THIRD_PARTY)
