# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: domains.py — oops/kb/domains.py

"""Static domain-profiling constants. Edit freely."""

# Transversal pillar modules: meaningful anchors but not applications.
PILLAR_MODULES: frozenset = frozenset({
    "product",
    "uom",
    "analytic",
    "contacts",
    "resource",
    "base_vat",
})

# Pure technical modules: excluded from domain profiling (noise).
EXCLUDED_TECHNICAL_MODULES: frozenset = frozenset({
    "base",
    "web",
    "mail",
    "bus",
})

# App technical name -> human label. Fallback: title-cased technical name.
DOMAIN_LABELS: dict = {
    "sale": "Sales",
    "account": "Accounting",
    "stock": "Inventory",
    "purchase": "Purchase",
    "mrp": "Manufacturing",
    "hr": "Human Resources",
    "project": "Project",
    "website": "Website",
    "point_of_sale": "Point of Sale",
}


def domain_label(app: str) -> str:
    """Return the human-readable label for an app technical name."""
    return DOMAIN_LABELS.get(app, app.replace("_", " ").title())
