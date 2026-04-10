# Requirements

::: oops.commands.requirements
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.requirements.check
    :command: main
    :prog_name: oops-requirements-check
    :depth: 2
    :style: table

**Examples:**

Update the addons table and commit if changed:

```bash
oops-requirements-update
```

Update without committing:

```bash
oops-requirements-update --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.requirements.update
    :command: main
    :prog_name: oops-requirements-update
    :depth: 2
    :style: table

**Examples:**

Update the addons table and commit if changed:

```bash
oops-requirements-update
```

Update without committing:

```bash
oops-requirements-update --no-commit
```
