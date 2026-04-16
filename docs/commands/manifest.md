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
    :prog_name: oops manifest check
    :depth: 2
    :style: table

**Examples:**

Check all manifests in the repository:

```bash
oops manifest check
```

Check specific addons by name:

```bash
oops manifest check sale_custom purchase_custom
```

Check from a directory (resolves the manifest automatically):

```bash
oops manifest check path/to/sale_custom
```

Show the suggested fix diff alongside each violation:

```bash
oops manifest check --diff
```

---

::: mkdocs-click:commands
    :module: oops.commands.manifest.fix
    :command: main
    :prog_name: oops manifest fix
    :depth: 2
    :style: table

**Examples:**

Fix all manifests in the repository:

```bash
oops manifest fix
```

Fix specific addons only:

```bash
oops manifest fix --names sale_custom,purchase_custom
```

Preview fixes without committing:

```bash
oops manifest fix --no-commit
```
