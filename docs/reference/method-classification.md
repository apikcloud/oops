# Method Classification Reference

## What classification does

The refactor pipeline assigns every method in an Odoo model to a canonical
section (`COMPUTE METHODS`, `DEFAULT METHODS`, etc.). The section controls:

- which `# === SECTION === #` header the method appears under in refactored files,
- which bucket the KB stores the method in (queryable by future tooling).

## Detection signals (in priority order)

Classification is decided by the first matching rule:

| Priority | Signal | Section |
|---|---|---|
| 1 | Method name is in `CRUD_NAMES` (`create`, `write`, `unlink`, `copy`, `name_search`, `_search`) | CRUD METHODS |
| 2 | Method name is in `DEFAULT_NAMES` (`default_get`) | DEFAULT METHODS |
| 3 | Decorator `@api.depends` | COMPUTE METHODS |
| 4 | Decorator `@api.onchange` | ONCHANGE METHODS |
| 5 | Decorator `@api.constrains` | CONSTRAINT METHODS |
| 6 | Field kwarg `compute=`, `inverse=`, or `search=` references this method | COMPUTE METHODS |
| 7 | Field kwarg `default=` references this method | DEFAULT METHODS |
| 8 | Field kwarg `selection=` references this method | SELECTION METHODS |
| 9 | Name starts with `action_` or `button_` | ACTION METHODS |
| 10 | Name starts with `_` | HELPER METHODS |
| 11 | (none of the above) | BUSINESS METHODS |

## Rationale for each rule

### CRUD METHODS

The ORM lifecycle methods (`create`, `write`, `unlink`, `copy`) are always
CRUD regardless of how they are decorated (e.g. `@api.model` on `name_search`).
Name is the authoritative signal; no decorator or kwarg can override it.

### DEFAULT METHODS

`default_get` is the standard ORM hook for programmatic field defaults. Like
CRUD methods, its role is fully determined by its name. Individual field
defaults expressed via `default=_method_name` on a field declaration are also
routed here — that kwarg is the only way to link an arbitrary method to this
section.

### COMPUTE METHODS

`@api.depends` is the canonical signal. When it is absent (a common pattern
for simple computes), the `compute=`, `inverse=`, or `search=` kwarg on the
corresponding field declaration is used instead. `inverse=` and `search=` are
grouped here because they are always paired with a compute field and share its
lifecycle.

### ONCHANGE METHODS

`@api.onchange` is the sole signal. There is no field-kwarg equivalent and no
naming convention.

### CONSTRAINT METHODS

`@api.constrains` is the sole signal. There is no field-kwarg equivalent and
no naming convention.

### SELECTION METHODS

**`selection=` on a field declaration is the only detection path.** Odoo
provides no decorator for selection providers, and there is no established
naming convention (`_get_*_selection`, `_selection_*`, etc. all appear in the
wild). Any name-based heuristic would produce false positives. A method that
provides selection values but is not referenced by a `selection=` kwarg will
fall through to HELPER or BUSINESS METHODS.

### ACTION METHODS and BUTTON METHODS

Methods prefixed `action_` are view actions (they typically return an
`ir.actions.*` dict). Methods prefixed `button_` are button handlers in forms
and lists. Both are grouped under ACTION METHODS because they share the same
trigger model (user gesture → server-side response) and the same documentation
convention.

### HELPER METHODS

Any private method (leading `_`) that does not match a higher-priority rule.
The catch-all for internal utilities.

### BUSINESS METHODS

Public methods (no leading `_`, no `action_`/`button_` prefix) that do not
match a higher-priority rule. Typically domain logic called from outside the
model.

## What is NOT a classification signal

### `@api.model`

This decorator marks that a method receives the model class as `self` rather
than a recordset. It is orthogonal to section: `default_get` is `@api.model`
and DEFAULT, `name_search` is `@api.model` and CRUD, a class-level helper is
`@api.model` and HELPER. Using it as a signal would produce a meaningless
"class-method" bucket that cuts across all real sections.

### `@api.multi` / `@api.one` (Odoo ≤ 12)

Legacy decorators that have no semantic meaning in Odoo ≥ 13 and are not
classification signals.

### Name prefixes for SELECTION METHODS

There is no canonical prefix (`_get_selection_*`, `_selection_*`, etc.). See
the SELECTION METHODS rationale above.

## Cross-file and cross-module detection

Field kwarg detection operates at three scopes, in order:

1. **Same class** — field and method declared in the same `ClassDef` body.
   Handled by a two-pass walk inside `analyse_file()`.
2. **Same module, different file** — field in `models/a.py`, method in
   `models/b.py`. Handled by a module-level pre-pass in the CLI that collects
   all field refs before per-file analysis runs.
3. **Different module** — field in module A, method in module B (cross-module
   override). Handled by the `field_refs` KB table, queried as a fallback when
   the local maps yield no result.

Decorator-based detection is always same-file (decorators are on the method
definition itself) and requires no cross-file logic.

## Extending the classification system

To add a new section:

1. Add a `METHOD_SECTION_*` constant in `src/oops/kb/scanner.py`.
2. Add the section name to `METHOD_SECTIONS` in `src/oops/io/refactor.py` at
   the desired output position.
3. Add a branch to `classify_method()` in `src/oops/kb/scanner.py` at the
   correct priority position.
4. If the section is driven by a field kwarg, add the kwarg to
   `FIELD_REF_KWARGS` and `KWARG_TO_SECTION`.
5. Add unit tests to `tests/test_kb_scanner.py::TestClassifyMethod`.
6. Update this document.
