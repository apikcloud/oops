# Manifest

!!! warning "Experimental"
    These commands are experimental. The rule set, options, and output format
    may change in future releases.

---

::: oops.commands.manifest
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.manifest.check
    :command: main
    :prog_name: oops-man-check
    :depth: 2
    :style: table

**Examples:**

Check all manifests in the repository:

```bash
oops-man-check
```

Check specific addons by name:

```bash
oops-man-check sale_custom purchase_custom
```

Check from a directory (resolves the manifest automatically):

```bash
oops-man-check path/to/sale_custom
```

Show the suggested fix diff alongside each violation:

```bash
oops-man-check --diff
```

---

::: mkdocs-click:commands
    :module: oops.commands.manifest.fix
    :command: main
    :prog_name: oops-man-fix
    :depth: 2
    :style: table

**Examples:**

Fix all manifests in the repository:

```bash
oops-man-fix
```

Fix specific addons only:

```bash
oops-man-fix --names sale_custom,purchase_custom
```

Preview fixes without committing:

```bash
oops-man-fix --no-commit
```
