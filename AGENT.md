# KB & Refactor Pipeline — Agent Handoff

> This document describes the current state of the `oops kb` pipeline, the
> decisions made during its design, and everything a local agent needs to
> continue development independently.

---

## 1. What Has Been Built

### 1.1 Overview

A three-command pipeline integrated into `oops` that builds a **symbol
knowledge base** (KB) from Odoo sources and uses it to refactor custom Odoo
modules: adding canonical section headers and minimal Google-style docstring
skeletons to every model file.

```
oops misc build-kb      →  builds ~/.cache/oops/kb/<version>.db (global, once per Odoo version)
oops addons refactor    →  rewrites model files, creates a git branch for PR; rebuilds project KB when stale
oops addons analyze     →  prints a structured summary of a module (text or JSON)
```

All three commands are marked **EXPERIMENTAL** (see module docstring + runtime warning).

### 1.2 Package Layout

```
oops/
├── kb/
│   ├── scanner.py      AST scanning; also hosts classify_method(), extract_field_refs(),
│   │                   build_module_field_refs(), and all METHOD_SECTION_* constants.
│   ├── store.py        SQLite persistence (KBReader, write_global_kb, write_project_kb)
│   │                   Schema v2: field_type + section on symbols, field_refs table.
│   └── resolve.py      Dependency graph resolution for symbol precedence
└── commands/
    ├── misc/
    │   └── build_global.py    CLI: oops misc build-kb
    └── addons/
        ├── refactor.py        CLI: oops addons refactor
        └── analyze.py         CLI: oops addons analyze
```

### 1.3 Command registration

The three KB commands are registered automatically via the Click subgroup
auto-discovery system — no `[project.scripts]` entry is needed:

- `oops misc build-kb` — `oops.commands.misc.build_global:main`
- `oops addons refactor` — `oops.commands.addons.refactor:main`
- `oops addons analyze` — `oops.commands.addons.analyze:main`

### 1.4 New dependency to declare

`libcst` is already listed in `oops` dependencies as `"libcst==0.4.*; python_version<'3.8'"`.
For Python ≥ 3.8, the version constraint must be relaxed. Update `pyproject.toml`:

```toml
# Replace:
"libcst==0.4.*; python_version<'3.8'",
# With:
"libcst>=0.4",
```

`sqlite3` is stdlib — no additional dependency needed.

---

## 2. Key Design Decisions

### 2.1 Two-Layer KB Architecture

| Layer | File | Lifecycle | Contents |
|-------|------|-----------|----------|
| Global | `~/.cache/oops/kb/kb_global_<version>.db` | Once per Odoo version | Odoo community + enterprise |
| Project | `<repo>/.oops-cache/kb_project_<version>.db` | Once per refactor session | Global + third-party + apik, filtered to installed modules |

**Rationale:** The global KB is expensive to build (full Odoo tree scan) and
changes only when the Odoo version changes. The project KB is cheap to rebuild
and is scoped to the actual modules installed in the production database.

### 2.2 SQLite over JSON

The project KB can grow to 50–150 MB for a full Odoo 17 installation. SQLite
allows partial queries (`get_symbol`) without loading the entire index into
memory, and provides native indexes on `(model, name, kind)`.

The KB is a **write-once / read-many** store: it is fully rebuilt on each
`kb-build-*` run (no incremental update). This simplifies the schema — no
versioning, no migrations.

### 2.3 Symbol Multi-Entry Model

A symbol (field or method) can be defined by multiple upstream modules. For
example, `type_id` on `sale.order` may exist in both `sale_order_type` (OCA)
and `apik_sale` (internal). The KB stores **all definitions** as separate rows:

```sql
PRIMARY KEY (model, name, kind, module)
```

`refactor.py` calls `resolve_symbol()` to select the most relevant entry
using the dependency graph.

### 2.4 Symbol Precedence via Dependency Graph

Precedence is determined by walking the `depends` graph of the custom module
being refactored (BFS, closest-first), not by a static tier ranking.

**Why BFS over static tier:** if `apik_sale` depends on `sale_order_type`,
then `sale_order_type` is "closer" to the custom module than a static
`third-party > apik` rule would suggest. The static tier ordering is only
used as a **tie-breaker** when two entries have the same BFS distance.

Static tier precedence (lower = higher priority): `third-party > apik > enterprise > odoo`.

A warning is emitted when the winning module is not in the dependency chain
at all — this signals a likely missing `depends` declaration in a third-party
manifest.

### 2.5 Third-Party Module Detection via Symlinks

Third-party (`OCA`) and internal generic (`apik`) modules are identified by
symlink resolution, not by manifest parsing or explicit configuration:

- Symlink real path contains `/.third-party/` → tier `third-party`
- Symlink real path contains `/apik-addons/`  → tier `apik`
- Non-symlink entries in addons directories   → custom modules (refactor targets)

This is robust to missing or incomplete `depends` declarations in OCA manifests.

### 2.6 AST for Analysis, libcst for Rewriting

- **AST (`ast` stdlib):** used for analysis only — extract model names, field
  assignments, method signatures, decorators. Fast, no side effects.
- **libcst:** used for rewriting — preserves original formatting, whitespace,
  and comments. Constructs section headers as `EmptyLine(comment=...)` attached
  to `leading_lines` of the first statement in each section.
- **super() detection:** done via `libcst.CSTVisitor` on the method body node,
  not AST, because libcst's `visit_Call` is more reliable for chained calls
  like `super().method(...)`.

### 2.7 Docstring Generation is LLM-Free

All docstring skeletons are generated deterministically from KB metadata:
- Method name
- Whether the method exists in the KB (`Inherit` vs new)
- Whether `super()` is called (`Inherit` vs `Override`)
- `Source:` line from KB (`origin`, `source_file`, `source_line`)

The `# TODO:` markers are the explicit handoff points for the developer.
The pipeline never interprets method bodies or infers business intent.

### 2.9 Method Classification

Method classification is determined by EITHER decorator-side OR field-side signals,
with decorator side taking priority. The shared function `classify_method()` in
`oops.kb.scanner` is the single source of truth for all classification logic —
both the KB scanner (for persisting `section` on KB methods) and the refactor
pipeline (`analyse_file`) call it.

Field-side signals are persisted as:
- A `section` column on the `symbols` table (for methods classified via field refs).
- A sibling `field_refs` table recording every string-literal field kwarg
  (`compute`, `inverse`, `search`, `default`, `selection`) and its target method.

Priority order (first match wins):
1. CRUD name → `CRUD METHODS`
2. `default_get` name → `DEFAULT METHODS`
3. `@api.depends` → `COMPUTE METHODS`
4. `@api.onchange` → `ONCHANGE METHODS`
5. `@api.constrains` → `CONSTRAINT METHODS`
6. Field ref `compute=`/`inverse=`/`search=` → `COMPUTE METHODS`
7. Field ref `default=` → `DEFAULT METHODS`
8. Field ref `selection=` → `SELECTION METHODS`
9. `action_`/`button_` prefix → `ACTION METHODS`
10. `_` prefix → `HELPER METHODS`
11. (else) → `BUSINESS METHODS`

See `docs/reference/method-classification.md` for the full rationale behind
each rule and guidance on extending the system.

### 2.8 Idempotency

The rewriter is designed to be idempotent: running `oops addons refactor` twice on
the same file produces no additional changes. This is achieved by:
1. Stripping **all** `leading_lines` from every statement during collection
   (including any section headers from a previous run).
2. Re-attaching headers cleanly via `_append_section`.
3. Never touching existing docstrings.

---

## 3. What Remains To Be Done

### 3.1 Immediate (blocking for first real use)

| # | Task | File | Notes |
|---|------|------|-------|
| 1 | **Fix `_is_section_header_stmt`** — the function is still referenced in the code but its logic was superseded by the strip-all approach. It can be simplified or removed. | `refactor.py` | Non-blocking but confusing |
| 2 | **Manifest `depends` for Odoo core** — `kb_build.py` `--global` mode does not currently filter by an allowed modules list. For very large Odoo installations this means indexing thousands of modules. Add a `--modules` option to `build_global` too for consistency (optional). | `build_global.py` | Low priority |
| 3 | **`.oops-cache` in `.gitignore`** — the project KB database should not be committed. Add `.oops-cache/` to the repo's `.gitignore` if not already present. | documentation | Trivial |
| 4 | ~~**`DEFAULT METHODS` section**~~ — **Done.** `default=` field kwarg is now detected and routes to `DEFAULT METHODS`. `default_get` by name also routes there. | `scanner.py` | ✓ |
| 5 | **`CONSTRAINTS` section** — `_sql_constraints` is a class-level list attribute, not a method. It should appear after `PRIVATE ATTRIBUTES` and before `COMPUTE METHODS`. Currently it falls into `_is_private_attr_stmt` (leading `_`). Structurally different from field-kwarg detection; out of scope for the field-linkage workstream. | `refactor.py` | Open |

### 3.2 Robustness improvements

| # | Task | Notes |
|---|------|-------|
| 6 | **Multi-class files** — files with multiple classes (e.g. `SaleOrder` + `SaleOrderLine` in the same file) are supported in analysis (`analyse_file` returns a list) but the rewriter processes classes in order. Test with a file containing 3+ classes. |
| 7 | **`_name` + `_inherit` simultaneously** — delegation inheritance (model copy). The field classification currently defaults to `INHERITED FIELDS`. Confirm this is acceptable on a real codebase. |
| 8 | **`AbstractModel` and `TransientModel`** — same section order applies. Confirmed in tests but not explicitly tested with `AbstractModel`. |
| 9 | **Source line drift** — the `source_line` in the KB is recorded at KB build time. If the upstream source changes between KB build and refactor run, the line number in the docstring will be stale. This is acceptable (it's informational only) but worth documenting in the generated comment. Consider adding `# KB generated at: <timestamp>` in the docstring or a note in the `Source:` line. |
| 10 | **Windows path handling** — `TIER_MARKERS` in `scanner.py` handles `\\` variants, but `tier_root_from_real_path` and the marker extraction assume POSIX paths. Test on Windows if relevant. |

### 3.3 Future features (post-first-use)

| # | Task | Notes |
|---|------|-------|
| 11 | **MkDocs output** — once the refactoring pass is stable, generate MkDocs documentation from the refactored files and the KB. The KB already contains all the metadata needed (model, origin, module, source). |
| 12 | **Map-reduce referential** — the KB is the foundation for the broader map-reduce pipeline discussed in the design phase. `resolve.py` (`build_depends_chain`) and `store.py` (`KBReader`) are the two interfaces that `refactor.py` uses and that the map-reduce agent will also use. |
| 13 | ~~**`SELECTION METHODS` detection**~~ — **Done.** `selection=` field kwarg is now detected and routes to `SELECTION METHODS`. The `selection=` kwarg is the sole reliable signal; name heuristics would produce false positives. | ✓ |
| 14 | **LLM enrichment pass (opt-in)** — an optional second pass that sends the `# TODO:` markers to an LLM with the method body as context, to generate richer docstring content. This should be a separate command (`oops-refactor-enrich`) so it is never run implicitly. |
| 15 | **KB invalidation check** — before running `oops addons refactor`, check whether the KB was built with a different Odoo version than the one in the repo's manifest (compare `meta.odoo_version`). Warn if stale. |

---

## 4. Module Interface Summary

### 4.1 `oops.kb.scanner`

```python
# Scan a single module directory
scan_module(module_dir: Path, origin: str, tier_root: Path) -> ScanResult

# Scan all modules under a tier root
scan_tier(tier_root: Path, origin: str, allowed_modules: set[str] | None) -> ScanResult

# Detect the two Odoo community addons roots
odoo_addons_roots(odoo_path: Path) -> list[Path]

# Resolve symlinks in a repo to their tier origin
resolve_symlink_tiers(repo_path: Path, allowed_modules: set[str] | None)
    -> dict[str, list[tuple[str, Path]]]

# Derive tier root from a real module path
tier_root_from_real_path(origin: str, real_path: Path) -> Path | None
```

`ScanResult` is a plain dict:
```python
{
    "modules": { module_name: {"origin": str, "depends": [str, ...]} },
    "symbols": [ {"model": str, "name": str, "kind": "field"|"method",
                  "origin": str, "module": str,
                  "source_file": str, "source_line": int}, ... ]
}
```

### 4.2 `oops.kb.store`

```python
# Write
write_global_kb(db_path, odoo_version, sources, scan_results)
write_project_kb(db_path, odoo_version, project, scope, sources, scan_results)

# Read
with KBReader(db_path) as kb:
    kb.get_meta()           -> dict[str, str]
    kb.get_modules()        -> dict[str, {origin, depends}]
    kb.get_symbol(model, name, kind)   -> list[dict]   # multi-entry
    kb.symbol_exists(model, name, kind) -> bool
    kb.model_exists(model)  -> bool
    kb.get_model_symbols(model, kind=None) -> list[dict]
    kb.get_sources()        -> dict[str, str]
```

### 4.3 `oops.kb.resolve`

```python
# Build the BFS dependency chain of a custom module
build_depends_chain(module: str, modules_index: dict) -> list[str]

# Select the most relevant KB entry for a symbol
resolve_symbol(entries: list[dict], custom_module: str, modules_index: dict)
    -> dict | None

# Format the Source: line for a docstring
format_source_line(entry: dict) -> str
# → "[odoo] addons/sale/models/sale_order.py, line 234"
```

### 4.4 `oops.commands.kb.refactor` — internal functions callable by other agents

```python
# Analyse a model file: returns ClassInfo list with classified symbols
analyse_file(py_file: Path, kb: KBReader, modules_index: dict, custom_module: str)
    -> list[ClassInfo]

# Apply all rewrites and return new source string (does not write to disk)
rewrite_file(py_file: Path, classes: list[ClassInfo]) -> str
```

`ClassInfo` and `SymbolInfo` are dataclasses defined in `refactor.py`:

```python
@dataclass
class SymbolInfo:
    name: str
    kind: str                 # 'field' | 'method'
    section: str              # canonical section name
    lineno: int
    has_docstring: bool
    has_super: bool
    super_methods: list[str]
    kb_entry: dict | None     # resolved KB entry (None = new symbol)
    is_override: bool         # in KB + no super() call

@dataclass
class ClassInfo:
    class_name: str
    model_name: str | None
    inherit: list[str]
    is_new_model: bool
    lineno: int
    symbols: list[SymbolInfo]
```

---

## 5. Database Schema Reference (v2)

Current schema version: `SCHEMA_VERSION = 2` in `store.py`.
On each KB write, data tables are dropped and re-created so column additions
always land on existing on-disk databases.

```sql
-- Both global and project KB use the same schema.

CREATE TABLE meta (
    key   TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL
);
-- Keys: layer, odoo_version, schema_version, generated_at,
--       project (project only), scope (project only)

CREATE TABLE sources (
    origin TEXT NOT NULL PRIMARY KEY,  -- odoo | enterprise | third-party | apik
    path   TEXT NOT NULL               -- absolute path to tier root
);

CREATE TABLE modules (
    name    TEXT NOT NULL PRIMARY KEY,
    origin  TEXT NOT NULL,
    depends TEXT NOT NULL DEFAULT '[]'  -- JSON array of module names
);

CREATE TABLE symbols (
    model       TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    kind        TEXT    NOT NULL,   -- 'field' | 'method'
    origin      TEXT    NOT NULL,
    module      TEXT    NOT NULL,
    source_file TEXT    NOT NULL,   -- relative to tier root in sources table
    source_line INTEGER NOT NULL,
    field_type  TEXT,               -- e.g. 'Boolean', NULL for methods
    section     TEXT,               -- canonical section name, NULL for fields
    PRIMARY KEY (model, name, kind, module)
);

CREATE INDEX idx_symbols_lookup ON symbols (model, name, kind);
CREATE INDEX idx_symbols_module ON symbols (module);
CREATE INDEX idx_modules_origin ON modules (origin);

-- Added in v2: tracks field kwarg → method references for cross-file classification.
CREATE TABLE field_refs (
    model         TEXT NOT NULL,
    field_name    TEXT NOT NULL,
    module        TEXT NOT NULL,
    kwarg         TEXT NOT NULL,   -- 'compute' | 'inverse' | 'search' | 'default' | 'selection'
    target_method TEXT NOT NULL,
    PRIMARY KEY (model, field_name, module, kwarg)
);

CREATE INDEX idx_field_refs_target ON field_refs (model, target_method);
```

---

## 6. CONVENTIONS.md Relationship

This pipeline implements the conventions defined in `CONVENTIONS.md` (in the
client repository). The mapping is:

| Convention section | Implemented by |
|--------------------|---------------|
| §3.1 Header format `# === NAME === #` | `_make_header()` in `refactor.py` |
| §3.2 Field sections (INHERITED / NEW / BASE) | `analyse_file()` + KB lookup |
| §3.3 Method section order | `METHOD_SECTIONS` constant in `refactor.py` |
| §4.1 Docstring on every method | `_inject_docstring()` in `refactor.py` |
| §4.2 Class docstring on new models | `_ensure_class_docstring()` logic |
| §4.3 Inherit template | `_method_docstring_lines()` when `kb_entry` + `has_super` |
| §4.4 Override template | `_method_docstring_lines()` when `kb_entry` + `is_override` |
| §4.7 New method template | `_method_docstring_lines()` when `kb_entry is None` |
| §4.8 Source location | `format_source_line()` in `resolve.py` |
| §5 KB architecture | `scanner.py`, `store.py`, two-layer DB files |
| §6.2 Method classification priority | `_classify_method()` in `refactor.py` |
| §6.3 super() detection | `_SuperDetector` libcst visitor in `refactor.py` |

**Open questions from CONVENTIONS.md §10 that affect the pipeline:**

- `COMPUTE METHODS` for native compute overrides: currently placed in
  `COMPUTE METHODS` by decorator priority (rule 2), not `CRUD METHODS`.
  This is the intended behaviour — confirm with team.
- `_sql_constraints` comparison against KB: not currently implemented.
  See task #5 above.

---

## 7. Testing Checklist

Before merging into `oops`, run through this checklist manually:

```bash
# 1. Build global KB (once per Odoo version)
oops misc build-kb --version 17.0

# 2. Dry-run refactor — also triggers project KB rebuild if stale
oops addons refactor addons/<module_name> --refresh --dry-run --verbose

# 3. Inspect KB stats
sqlite3 .oops-cache/kb.db \
    "SELECT origin, count(*) FROM modules GROUP BY origin;"
sqlite3 .oops-cache/kb.db \
    "SELECT kind, count(*) FROM symbols GROUP BY kind;"

# 4. Real refactor on one module
oops addons refactor addons/<module_name> --verbose

# 5. Inspect result
git diff HEAD

# 6. Idempotency (should produce 0 changes)
oops addons refactor addons/<module_name> --no-branch --dry-run
# Expected: no "would rewrite" lines

# 7. Syntax check
python -m py_compile addons/<module_name>/models/*.py

# 8. Structured module summary (read-only, optional)
oops addons analyze addons/<module_name>
```

---

## 8. Known Limitations

- **Symlink detection is POSIX-only.** The `TIER_MARKERS` dict handles
  backslash variants but has not been tested on Windows.
- **libcst version sensitivity.** The `visit()` API and some node types
  differ between libcst versions. Tested with libcst ≥ 1.0.
- **super() detection is syntactic only.** `super().method()` is detected;
  `super(ClassName, self).method()` (old-style) is not. This is acceptable
  for Odoo 14+ codebases which use the new-style API exclusively.
- **No handling of `@api.model` or `@api.model_create_multi`.** These
  decorators do not affect section classification but may affect docstring
  `Args:` content. The `# TODO:` marker covers this.
- **Field overrides without redeclaration.** In Odoo, you can override
  a field attribute using `field_name = fields.Char(string='New label')`.
  The pipeline correctly classifies this as `INHERITED FIELDS` when the
  field name is found in the KB. If the KB lookup fails (missing KB entry),
  it falls to `NEW FIELDS` and a `# PIPELINE: classification uncertain`
  comment is NOT currently emitted for fields (only for ambiguous methods).
  Consider adding this for fields too.
