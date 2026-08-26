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


def classify_addon(
    author: str,
    technical_name: str,
    submodule_org: str,
    *,
    project_author: Optional[str] = None,
    project_prefix: Optional[str] = None,
    github_owner: Optional[str] = None,
) -> str:
    """Classify a project-root addon as custom/oca/third-party.

    Pure function — mirrors the priority order previously inline in
    io/file.py:enrich_addon() (first match wins):
    1. "(OCA)" in author -> "oca"
    2. author == project_author -> "custom"
    3. technical_name starts with project_prefix -> "custom"
    4. submodule_org == "OCA" -> "oca"; submodule_org == github_owner -> "custom"
    5. fallback -> "third-party"

    Args:
        author: The addon's manifest ``author`` string.
        technical_name: The addon's technical (directory) name.
        submodule_org: The submodule's GitHub org (first path segment of its
            remote), or "" if the addon isn't inside a submodule.
        project_author: This project's configured manifest author to match
            against (``config.manifest.author`` on the CLI side), or None.
        project_prefix: This project's configured addon name prefix
            (``config.project.prefix``), or None.
        github_owner: This project's configured GitHub owner
            (``config.github.owner``), or None.
    """
    if "(OCA)" in author:
        return "oca"
    if project_author and author == project_author:
        return "custom"
    if project_prefix and technical_name.startswith(project_prefix):
        return "custom"
    if submodule_org:
        if submodule_org == "OCA":
            return "oca"
        if github_owner and submodule_org == github_owner:
            return "custom"
    return "third-party"
