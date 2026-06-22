# Submodules

::: oops.commands.submodules
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.add
    :command: main
    :prog_name: oops submodules add
    :depth: 2
    :style: table

**Examples:**

Add a submodule and interactively pick which addons to symlink:

```bash
oops submodules add https://github.com/OCA/server-ux.git 18.0
```

Add a submodule and symlink only specific addons (non-interactive):

```bash
oops submodules add https://github.com/OCA/server-ux.git 18.0 --addons mass_editing,web_notify
```

Add and symlink all addons without prompting:

```bash
oops submodules add https://github.com/OCA/server-ux.git 18.0 --force
```

Add as a pull-request submodule:

```bash
oops submodules add https://github.com/OCA/server-ux.git 18.0 --pull-request
```

Stage changes without committing:

```bash
oops submodules add https://github.com/OCA/server-ux.git 18.0 --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.branch
    :command: main
    :prog_name: oops submodules branch
    :depth: 2
    :style: table

**Examples:**

Set a default branch for all submodules missing one (branch auto-detected from odoo_version.txt):

```bash
oops submodules branch
```

Set a specific branch explicitly:

```bash
oops submodules branch 18.0
```

Skip pull-request submodules:

```bash
oops submodules branch 18.0 --skip-pr
```

Apply without confirmation prompt:

```bash
oops submodules branch 18.0 --force
```

Set branch without committing:

```bash
oops submodules branch 18.0 --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.check
    :command: main
    :prog_name: oops submodules check
    :depth: 2
    :style: table

**Examples:**

Run all configured checks and report issues:

```bash
oops submodules check
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.clean
    :command: main
    :prog_name: oops submodules clean
    :depth: 2
    :style: table

**Examples:**

Launch the interactive cleanup (picks a reset target, then wipes and re-inits):

```bash
oops submodules clean
```

Same command, via the alias:

```bash
oops-i-did-it-again
```

This command is fully interactive. Cancel any prompt to abort without changes.

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.fix
    :command: main
    :prog_name: oops submodules fix
    :depth: 2
    :style: table

**Examples:**

Preview what would be fixed without applying changes:

```bash
oops submodules fix --dry-run
```

Fix issues and commit the result:

```bash
oops submodules fix
```

Fix without committing:

```bash
oops submodules fix --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.init
    :command: main
    :prog_name: oops submodules init
    :depth: 2
    :style: table

**Examples:**

Initialize all submodules with the default 4 parallel jobs:

```bash
oops submodules init
```

Speed up initialization on a large project:

```bash
oops submodules init --jobs 8
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.prune
    :command: main
    :prog_name: oops submodules prune
    :depth: 2
    :style: table

**Examples:**

Remove unused submodules (interactive confirmation):

```bash
oops submodules prune
```

Apply without confirmation prompt:

```bash
oops submodules prune --force
```

Remove without committing:

```bash
oops submodules prune --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.rename
    :command: main
    :prog_name: oops submodules rename
    :depth: 2
    :style: table

**Examples:**

Interactively select which submodules to rename (shows the plan before applying):

```bash
oops submodules rename
```

Rename all submodules without prompting:

```bash
oops submodules rename --force
```

Rename specific submodules by name:

```bash
oops submodules rename OCA/server-ux OCA/server-tools
```

Rename without committing:

```bash
oops submodules rename --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.remove
    :command: main
    :prog_name: oops submodules remove
    :depth: 2
    :style: table

**Examples:**

Select submodules to remove from an interactive indexed menu:

```bash
oops submodules remove
```

Remove a specific submodule by name:

```bash
oops submodules remove OCA/server-ux
```

Apply without confirmation prompt:

```bash
oops submodules remove OCA/server-ux --force
```

Remove without committing:

```bash
oops submodules remove OCA/server-ux --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.replace
    :command: main
    :prog_name: oops submodules replace
    :depth: 2
    :style: table

**Examples:**

Replace a submodule with a new repository (interactive confirmation):

```bash
oops submodules replace OCA/old-repo https://github.com/OCA/new-repo.git 18.0
```

Apply without confirmation prompt:

```bash
oops submodules replace OCA/old-repo https://github.com/OCA/new-repo.git 18.0 --force
```

Replace without committing:

```bash
oops submodules replace OCA/old-repo https://github.com/OCA/new-repo.git 18.0 --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.rewrite
    :command: main
    :prog_name: oops submodules rewrite
    :depth: 2
    :style: table

**Examples:**

Interactively select which submodules to rewrite (shows the plan before applying):

```bash
oops submodules rewrite
```

Rewrite all paths non-interactively:

```bash
oops submodules rewrite --force
```

Rewrite to a custom base directory without prompting:

```bash
oops submodules rewrite --base-dir .third-party --force
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.show
    :command: main
    :prog_name: oops submodules show
    :depth: 2
    :style: table

**Examples:**

Show all submodules with their last commit info:

```bash
oops submodules show
```

Show only pull-request submodules:

```bash
oops submodules show --pull-request
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.update
    :command: main
    :prog_name: oops submodules update
    :depth: 2
    :style: table

**Examples:**

Update all submodules to their latest upstream commit:

```bash
oops submodules update
```

Update a single submodule by name:

```bash
oops submodules update apikcloud/apik-addons
```

Apply without confirmation prompt:

```bash
oops submodules update --force
```

Skip pull-request submodules:

```bash
oops submodules update --skip-pr
```

Update only pull-request submodules:

```bash
oops submodules update --only-pr
```

Update without committing:

```bash
oops submodules update --no-commit
```
