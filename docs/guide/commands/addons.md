# Addons

::: oops.commands.addons
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.addons.add
    :command: main
    :prog_name: oops addons add
    :depth: 2
    :style: table

**Examples:**

Add `mass_editing` and `web_notify` from any tracked submodule:

```bash
oops addons add mass_editing,web_notify
```

Stage the symlinks without committing:

```bash
oops addons add sale_management --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.analyze
    :command: main
    :prog_name: oops addons analyze
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the KB pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Print a text summary of a single module:

```bash
oops addons analyze plant_nursery
```

Emit JSON for downstream tooling:

```bash
oops addons analyze plant_nursery --format json | jq '.modules[0].models[0]'
```

### JSON output — IR v2

The `--format json` payload is a clean **intermediate representation** stamped
with `metadata.schema_version: 2`. Per module it carries **four flat sibling
lists** of id-addressable nodes — `models`, `fields`, `methods`, `views` — wired
together by id references rather than nesting:

- Every node has a module-qualified `id`
  (`plant_nursery:plant.order`, `…#field:dev_hours`, `…#method:_compute_total`;
  views use their globally-unique `xml_id`).
- A field's `model`/`compute`/`comodel`, a method's `model`, and a view's
  `model`/`inherit_id` are **id references**. Cross-module override targets are
  kept as descriptive references (`overrides`/`inherited_from` with
  `origin_module` + `origin` + `source_file`) — never dropped, even when the
  ancestor lives outside the scanned repo.
- Content is captured: method `docstring`/`signature`/`decorators`, field
  `label`/`help`/`selection`/`default`, model `description`/`docstring`. A
  non-literal kwarg (variable, f-string, call) sets `dynamic: true` with `null`
  values — never guessed.

```bash
# group the flat lists back into a per-model view (a renderer projection)
oops addons analyze plant_nursery --format json \
  | jq '.modules[0] | {methods, fields, views}'
```

The `manifest`, `metrics` and `loc` blocks carry **raw values only**. Their
labels, kinds and units live once in the descriptor registry
(`src/oops/output/schema/analyze_ir_v2.json`), keyed by metric name — each
formatter joins values to descriptors at render time. Aggregate `metrics` are
**derived** from the flat lists (e.g. `metrics.overridden_methods` equals the
count of `methods` with `is_override == true`).

One provenance vocabulary is used everywhere:
`origin ∈ {core, enterprise, oca, third_party, custom}` (the field is `origin`,
or `inherit_origin` for what an entity inherits/overrides).

**Recorded limitations** (also in `metadata.limitations`):

- `oca` is a valid enum member but **unpopulated** — all submodule code is
  currently folded into `third_party`.
- `controllers/`, `wizard/`, `report/` and `data` are **not analysed**; each
  module lists its uncovered areas under `not_analysed`.

### HTML output — self-contained SPA

`--format html` produces a single portable file with no external dependencies —
openable over `file://` and shareable as an attachment.  The page embeds the
full UI bundle (CSS + JS) and the JSON payload inline.

```bash
# write to a path
oops addons analyze plant_nursery --format html --output /tmp/plant_nursery.html

# open immediately (default: temp file)
oops addons analyze plant_nursery --format html
```

### Domain profile

Each module's JSON payload includes a `domain_profile` block that quantifies
how much the module touches each Odoo functional domain (Sales, Accounting,
Inventory…) and which transversal pillars (product, analytic…) it relies on.

```json
{
  "domain_profile": {
    "domains": [
      {"domain": "sale", "label": "Sales", "weight_raw": 12.5,
       "score_proportional": 0.63, "score_relative": 1.0,
       "indicators": {"models_extended": 1, "methods_override": 2, ...}}
    ],
    "pillars": [
      {"domain": "product", "label": "Product", "weight_raw": 4.0, ...}
    ],
    "custom_models": 0
  }
}
```

Scoring weights can be tuned via `analyze.domain_weights` in `.oops.yaml`.
See [`AnalyzeConfig`](../../reference/core/config.md) for the full weight list
and [`kb/domains`](../../reference/kb/domains.md) for the domain/pillar
classification tables.

Analyse several modules in one invocation:

```bash
oops addons analyze plant_nursery plant_orders
```

Force a KB rebuild before analysing:

```bash
oops addons analyze plant_nursery --refresh
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.compare
    :command: main
    :prog_name: oops addons compare
    :depth: 2
    :style: table

**Examples:**

Check which addons from a list are missing or extra in the repo root:

```bash
oops addons compare "sale,purchase,account"
```

Remove extra local symlinks not in the provided list:

```bash
oops addons compare "sale,purchase" --delete
```

Compare against a file and skip the commit:

```bash
oops addons compare "$(cat addons.txt)" --delete --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.diff
    :command: main
    :prog_name: oops addons diff
    :depth: 2
    :style: table

**Examples:**

Show modified addons since the latest tag:

```bash
oops addons diff
```

Compare against a specific tag:

```bash
oops addons diff --tag v1.2.0
```

Compare against the last 5 commits:

```bash
oops addons diff --commits 5
```

Write the migration script to `migrate.sh` and commit:

```bash
oops addons diff --save
```

Write the migration script without committing:

```bash
oops addons diff --save --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.download
    :command: main
    :prog_name: oops addons download
    :depth: 2
    :style: table

**Examples:**

Download all addons from a branch:

```bash
oops addons download https://github.com/OCA/server-ux.git 18.0
```

Download only specific addons:

```bash
oops addons download https://github.com/OCA/server-ux.git 18.0 --addons mass_editing
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.list
    :command: main
    :prog_name: oops addons list
    :depth: 2
    :style: table

**Examples:**

Display the addon table:

```bash
oops addons list
```

Export as JSON for scripting:

```bash
oops addons list --format json
```

Limit to a single submodule:

```bash
oops addons list -n apikcloud/apik-addons
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.manage
    :command: main
    :prog_name: oops addons manage
    :depth: 2
    :style: table

**Examples:**

Open the interactive picker to link or unlink addons:

```bash
oops addons manage
```

Apply changes without committing:

```bash
oops addons manage --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.materialize
    :command: main
    :prog_name: oops addons materialize
    :depth: 2
    :style: table

**Examples:**

Preview all symlinks that would be materialized:

```bash
oops addons materialize --dry-run
```

Materialize all symlinks at the repository root:

```bash
oops addons materialize
```

Materialize only specific addons:

```bash
oops addons materialize --include my_addon,other_addon
```

Materialize all symlinks except specific ones:

```bash
oops addons materialize --exclude legacy_addon
```

Materialize without committing:

```bash
oops addons materialize --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.refactor
    :command: main
    :prog_name: oops addons refactor
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the KB pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Rewrite a single module on a dedicated `refactor/doc-<module>` branch with one commit:

```bash
oops addons refactor my_module
```

Rewrite several modules in one run (one commit per module on `refactor/doc-multi`):

```bash
oops addons refactor my_module other_module
```

Preview the changes without writing any file:

```bash
oops addons refactor my_module --dry-run
```

Stay on the current branch and skip the commit (edits are staged):

```bash
oops addons refactor my_module --no-branch --no-commit
```

Force a project KB rebuild before running:

```bash
oops addons refactor my_module --refresh
```

Use an external KB database (skips the project-KB freshness check and `--refresh`):

```bash
oops addons refactor my_module --kb /path/to/project_kb.db
```
