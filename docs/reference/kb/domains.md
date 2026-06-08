# Domains

::: oops.kb.domains

---

## Classification tables

### Pillar modules

Modules in `PILLAR_MODULES` are meaningful cross-cutting anchors (product,
analytic, uom…) but are not Odoo applications.  A model whose creator lives
in a pillar is attributed to that pillar rather than to a domain.

### Excluded technical modules

Modules in `EXCLUDED_TECHNICAL_MODULES` (base, web, mail, bus) are excluded
from domain profiling entirely — models created by these modules are treated
as noise and skipped.

### Domain labels

`DOMAIN_LABELS` maps Odoo app technical names to human-readable labels used
in the UI and JSON output.  Apps not listed fall back to a title-cased version
of their technical name (e.g. `fleet` → `Fleet`).

To add a domain label, extend `DOMAIN_LABELS` in `kb/domains.py`.

---

## Customising classification

`PILLAR_MODULES`, `EXCLUDED_TECHNICAL_MODULES`, and `DOMAIN_LABELS` are all
module-level constants — edit them directly.  No config key controls them at
runtime; they are part of the codebase.
