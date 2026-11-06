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

from fnmatch import fnmatchcase

from oops_engine.compat import Dict, List, Optional
from oops_engine.exceptions import ClassificationConflict

# origin ∈ { core, enterprise, oca, third_party, custom }
ORIGIN_CORE = "core"
ORIGIN_ENTERPRISE = "enterprise"
ORIGIN_OCA = "oca"
ORIGIN_THIRD_PARTY = "third_party"
ORIGIN_CUSTOM = "custom"

# Addon classification vocabulary (``Addon.classification``).
CLASSIFICATIONS = ("custom", "oca", "third-party")

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
    "odoo_core": ORIGIN_CORE,  # community/odoo/addons tier
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


def match_classification(technical_name: str, rules: Optional[Dict[str, List[str]]]) -> Optional[str]:
    """Return the class explicitly assigned to an addon, if any.

    Patterns are ``fnmatch`` globs matched case-sensitively against the whole
    technical name, so a pattern without wildcard is an exact name. An exact
    name beats any glob; matches at the same level in two classes conflict.

    Args:
        technical_name: The addon's technical (directory) name.
        rules: Class name -> patterns, or None.

    Returns:
        The matching class, or None if no rule applies.

    Raises:
        ClassificationConflict: The addon matches several classes at the same
            level. Only an actual name can reveal overlapping globs, so this
            cannot be fully checked when the configuration is loaded.
    """
    if not rules:
        return None

    exact = sorted(name for name, patterns in rules.items() if technical_name in patterns)
    matched = exact or sorted(
        name for name, patterns in rules.items() if any(fnmatchcase(technical_name, p) for p in patterns)
    )
    if len(matched) > 1:
        raise ClassificationConflict(
            f"Addon '{technical_name}' matches several classification rules: {', '.join(matched)}"
        )
    return matched[0] if matched else None


def classify_addon(
    author: str,
    technical_name: str,
    submodule_org: str,
    *,
    project_author: Optional[str] = None,
    project_prefix: Optional[str] = None,
    github_owner: Optional[str] = None,
    overrides: Optional[Dict[str, List[str]]] = None,
) -> str:
    """Classify a project-root addon as custom/oca/third-party.

    Pure function (first match wins):
    1. overrides match technical_name -> that class (see match_classification)
    2. "(OCA)" in author -> "oca"
    3. author == project_author -> "custom"
    4. technical_name starts with project_prefix -> "custom"
    5. submodule_org == "OCA" -> "oca"; submodule_org == github_owner -> "custom"
    6. fallback -> "third-party"

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
        overrides: This project's explicit class -> patterns rules
            (``config.classification``), or None.
    """
    explicit = match_classification(technical_name, overrides)
    if explicit:
        return explicit
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
