# Requirements

::: oops.commands.requirements
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

## How it works

Both commands scan every addon manifest at the project root and collect
`external_dependencies["python"]` entries. The collected names are normalized to
their pip equivalents, deduplicated, and version-merged before being compared to
(or used to rewrite) the current `requirements.txt`.

## Merging rules

When multiple addons declare constraints for the same package, they are merged
before comparison:

| #   | Case                        | Behaviour                                                                                                      |
| --- | --------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1   | Bare name (no operator)     | Kept as-is, deduplicated across addons                                                                         |
| 2   | Single floor (`>=` / `>`)   | Kept as-is                                                                                                     |
| 3   | Single ceil (`<=` / `<`)    | Kept as-is                                                                                                     |
| 4   | Multiple floors             | Highest version wins (most restrictive)                                                                        |
| 5   | Multiple ceils              | Lowest version wins (most restrictive)                                                                         |
| 6   | Floor + ceil                | Merged as `pkg>=floor,<ceil`                                                                                   |
| 7   | `>` vs `>=` at same version | Strict operator wins (`>` beats `>=`, `<` beats `<=`)                                                          |
| 8   | `==` pin                    | Kept as-is; if a version range also exists for the same package, both are emitted — human arbitration required |
| 9   | Git dep (e.g. `pkg@git+…`)  | No operator detected → treated as bare name, passed through unchanged                                          |
| 10  | Name mapping                | Import names are normalized to pip names before version processing (see below)                                 |
| 11  | Final output                | Alphabetically sorted                                                                                          |

## Name mapping

Import names are mapped to their canonical pip package names before any version
processing. The built-in defaults are:

| Import name           | pip name              |
| --------------------- | --------------------- |
| `dateutil`            | `python-dateutil`     |
| `jours-feries-france` | `jours_feries_france` |
| `PIL`                 | `Pillow`              |
| `shopify`             | `ShopifyAPI`          |
| `stdnum`              | `python-stdnum`       |

Additional mappings can be declared in `.oops.yaml`:

```yaml
requirements:
  python_requirements_mapping:
    mylib: my-lib-on-pypi
```

::: mkdocs-click:commands
    :module: oops.commands.requirements.check
    :command: main
    :prog_name: oops requirements check
    :depth: 2
    :style: table

**Examples:**

Update the addons table and commit if changed:

```bash
oops requirements update
```

Update without committing:

```bash
oops requirements update --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.requirements.update
    :command: main
    :prog_name: oops requirements update
    :depth: 2
    :style: table

**Examples:**

Update the addons table and commit if changed:

```bash
oops requirements update
```

Update without committing:

```bash
oops requirements update --no-commit
```
