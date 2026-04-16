# Project

::: oops.commands.project
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.project.check
    :command: main
    :prog_name: oops project check
    :depth: 2
    :style: table

**Examples:**

Run project checks and report warnings and errors:

```bash
oops project check
```

Exit non-zero on warnings as well:

```bash
oops project check --strict
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.exclude
    :command: main
    :prog_name: oops project exclude
    :depth: 2
    :style: table

**Examples:**

Write the pre-commit exclusion file and commit:

```bash
oops project exclude
```

Write the file without committing:

```bash
oops project exclude --no-commit
```

Run as a pre-commit hook (raises an error if the exclusion list changed, prompting a re-run):

```bash
oops project exclude --hook
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.init
    :command: main
    :prog_name: oops project init
    :depth: 2
    :style: table

**Examples:**

Generate `docker-compose.yml`, `.config/odoo.conf`, and a VSCode workspace file for the current project:

```bash
oops project init
```

Include the maildev catch-all SMTP service:

```bash
oops project init --with-maildev
```

Include the SFTP service:

```bash
oops project init --with-sftp
```

Disable `--dev=all` (production-like setup):

```bash
oops project init --no-dev
```

Use a custom host port:

```bash
oops project init --port 8072
```

Skip generating the VSCode workspace file:

```bash
oops project init --without-workspace
```

Include the Odoo sources as folders in the generated workspace:

```bash
oops project init --include-sources
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.show
    :command: main
    :prog_name: oops project show
    :depth: 2
    :style: table

**Examples:**

Display the full project summary:

```bash
oops project show
```

Include the latest GitHub Actions run:

```bash
oops project show --token $GH_TOKEN
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.sync
    :command: main
    :prog_name: oops project sync
    :depth: 2
    :style: table

**Examples:**

Sync files from the configured remote repository with confirmation prompt:

```bash
oops project sync
```

Preview the diff without applying any changes:

```bash
oops project sync --dry-run
```

Apply changes without confirmation:

```bash
oops project sync --force
```

Sync from a specific branch:

```bash
oops project sync --branch develop
```

Sync only specific files/folders (overrides config):

```bash
oops project sync -F .pre-commit-config.yaml -F .github/workflows
```

---

::: mkdocs-click:commands
    :module: oops.commands.project.update
    :command: main
    :prog_name: oops project update
    :depth: 2
    :style: table

**Examples:**

Interactively select a new Odoo image:

```bash
oops project update
```

Pick the latest image automatically without prompting:

```bash
oops project update --force
```
