# Readme

::: oops.commands.readme
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.readme.update
    :command: main
    :prog_name: oops readme update
    :depth: 2
    :style: table

**Examples:**

Update the addons table and commit if changed:

```bash
oops readme update
```

Update without committing:

```bash
oops readme update --no-commit
```
