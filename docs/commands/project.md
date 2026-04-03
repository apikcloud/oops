# Project

::: mkdocs-click:commands
    :module: oops.commands.project.info
    :command: main
    :prog_name: oops-pro-info
    :depth: 2
    :style: table

**Examples:**

Display the full project summary:

```bash
oops-pro-info
```

Include the latest GitHub Actions run:

```bash
oops-pro-info --token $GH_TOKEN
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.check
    :command: main
    :prog_name: oops-pro-check
    :depth: 2
    :style: table

**Examples:**

Run project checks and report warnings and errors:

```bash
oops-pro-check
```

Exit non-zero on warnings as well:

```bash
oops-pro-check --strict
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.update
    :command: main
    :prog_name: oops-pro-update
    :depth: 2
    :style: table

**Examples:**

Interactively select a new Odoo image:

```bash
oops-pro-update
```

Pick the latest image automatically without prompting:

```bash
oops-pro-update --force
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.exclusions
    :command: main
    :prog_name: oops-pro-exclude
    :depth: 2
    :style: table

**Examples:**

Write the pre-commit exclusion file and commit:

```bash
oops-pro-exclude
```

Write the file without committing:

```bash
oops-pro-exclude --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.sync
    :command: main
    :prog_name: oops-pro-sync
    :depth: 2
    :style: table

**Examples:**

XXX:

```bash
oops-pro-sync
```
```