# Project

::: oops.commands.project
    options:
      show_root_heading: false
      show_docstring_modules: true 

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
    :module: oops.commands.project.exclude
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
    :module: oops.commands.project.init
    :command: main
    :prog_name: oops-pro-init
    :depth: 2
    :style: table

**Examples:**

Generate `docker-compose.yml` and `config/odoo.conf` for the current project:

```bash
oops-pro-init
```

Include the maildev catch-all SMTP service:

```bash
oops-pro-init --with-maildev
```

Include the SFTP service:

```bash
oops-pro-init --with-sftp
```

Disable `--dev=all` (production-like setup):

```bash
oops-pro-init --no-dev
```

Use a custom host port:

```bash
oops-pro-init --port 8072
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.show
    :command: main
    :prog_name: oops-pro-show
    :depth: 2
    :style: table

**Examples:**

Display the full project summary:

```bash
oops-pro-show
```

Include the latest GitHub Actions run:

```bash
oops-pro-show --token $GH_TOKEN
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.sync
    :command: main
    :prog_name: oops-pro-sync
    :depth: 2
    :style: table

**Examples:**

Sync files from the configured remote repository with confirmation prompt:

```bash
oops-pro-sync
```

Preview the diff without applying any changes:

```bash
oops-pro-sync --dry-run
```

Apply changes without confirmation:

```bash
oops-pro-sync --force
```

Sync from a specific branch:

```bash
oops-pro-sync --branch develop
```

Sync only specific files/folders (overrides config):

```bash
oops-pro-sync -F .pre-commit-config.yaml -F .github/workflows
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
