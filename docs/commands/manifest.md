# Manifest

!!! warning "Experimental"
    These commands are experimental. The rule set, options, and output format
    may change in future releases.

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

Check specific addons only:

```bash
oops-man-check --names sale_custom,purchase_custom
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
