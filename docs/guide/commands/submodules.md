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

Add a submodule and create symlinks for all its addons automatically:

```bash
oops submodules add https://github.com/OCA/server-ux.git 18.0 --auto-symlinks
```

Add a submodule and symlink only specific addons:

```bash
oops submodules add https://github.com/OCA/server-ux.git 18.0 --addons mass_editing,web_notify
```

Preview planned actions without touching the repository:

```bash
oops submodules add https://github.com/OCA/server-ux.git 18.0 --dry-run
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.branch
    :command: main
    :prog_name: oops submodules branch
    :depth: 2
    :style: table

**Examples:**

Set a default branch for all submodules missing one:

```bash
oops submodules branch --branch 18.0
```

Skip pull-request submodules during the fix:

```bash
oops submodules branch --branch 18.0 --skip-pr
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

Remove stale directories and re-init submodules:

```bash
oops submodules clean
```

Hard-reset the repo before cleaning:

```bash
oops submodules clean --reset
```

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

Preview which submodules would be removed:

```bash
oops submodules prune --dry-run
```

Remove unused submodules and commit:

```bash
oops submodules prune
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.rename
    :command: main
    :prog_name: oops submodules rename
    :depth: 2
    :style: table

**Examples:**

Preview renames without applying them:

```bash
oops submodules rename --dry-run
```

Rename all without interactive confirmation:

```bash
oops submodules rename --no-prompt
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

Preview what would be removed without making changes:

```bash
oops submodules remove --dry-run
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

Replace a submodule with a new repository:

```bash
oops submodules replace OCA/old-repo https://github.com/OCA/new-repo.git 18.0
```

Preview the replacement without making changes:

```bash
oops submodules replace OCA/old-repo https://github.com/OCA/new-repo.git 18.0 --dry-run
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.rewrite
    :command: main
    :prog_name: oops submodules rewrite
    :depth: 2
    :style: table

**Examples:**

Preview path rewrites without applying them:

```bash
oops submodules rewrite --dry-run
```

Rewrite all paths non-interactively:

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

Skip pull-request submodules:

```bash
oops submodules update --skip-pr
```
