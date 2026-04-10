# Submodules

::: oops.commands.submodules
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.init
    :command: main
    :prog_name: oops-sub-init
    :depth: 2
    :style: table

**Examples:**

Initialize all submodules with the default 4 parallel jobs:

```bash
oops-sub-init
```

Speed up initialization on a large project:

```bash
oops-sub-init --jobs 8
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.add
    :command: main
    :prog_name: oops-sub-add
    :depth: 2
    :style: table

**Examples:**

Add a submodule and create symlinks for all its addons automatically:

```bash
oops-sub-add https://github.com/OCA/server-ux.git -b 18.0 --auto-symlinks
```

Add a submodule and symlink only specific addons:

```bash
oops-sub-add https://github.com/OCA/server-ux.git -b 18.0 --addons mass_editing,web_notify
```

Preview planned actions without touching the repository:

```bash
oops-sub-add https://github.com/OCA/server-ux.git -b 18.0 --dry-run
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.show
    :command: main
    :prog_name: oops-sub-show
    :depth: 2
    :style: table

**Examples:**

Show all submodules with their last commit info:

```bash
oops-sub-show
```

Show only pull-request submodules:

```bash
oops-sub-show --pull-request
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.check
    :command: main
    :prog_name: oops-sub-check
    :depth: 2
    :style: table

**Examples:**

Run all configured checks and report issues:

```bash
oops-sub-check
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.fix
    :command: main
    :prog_name: oops-sub-fix
    :depth: 2
    :style: table

**Examples:**

Preview what would be fixed without applying changes:

```bash
oops-sub-fix --dry-run
```

Fix issues and commit the result:

```bash
oops-sub-fix
```

Fix without committing:

```bash
oops-sub-fix --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.update
    :command: main
    :prog_name: oops-sub-update
    :depth: 2
    :style: table

**Examples:**

Update all submodules to their latest upstream commit:

```bash
oops-sub-update
```

Update a single submodule by name:

```bash
oops-sub-update apikcloud/apik-addons
```

Skip pull-request submodules:

```bash
oops-sub-update --skip-pr
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.prune
    :command: main
    :prog_name: oops-sub-prune
    :depth: 2
    :style: table

**Examples:**

Preview which submodules would be removed:

```bash
oops-sub-prune --dry-run
```

Remove unused submodules and commit:

```bash
oops-sub-prune
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.rename
    :command: main
    :prog_name: oops-sub-rename
    :depth: 2
    :style: table

**Examples:**

Preview renames without applying them:

```bash
oops-sub-rename --dry-run
```

Rename all without interactive confirmation:

```bash
oops-sub-rename --no-prompt
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.replace
    :command: main
    :prog_name: oops-sub-replace
    :depth: 2
    :style: table

**Examples:**

Replace a submodule with a new repository:

```bash
oops-sub-replace OCA/old-repo https://github.com/OCA/new-repo.git 18.0
```

Preview the replacement without making changes:

```bash
oops-sub-replace OCA/old-repo https://github.com/OCA/new-repo.git 18.0 --dry-run
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.rewrite
    :command: main
    :prog_name: oops-sub-rewrite
    :depth: 2
    :style: table

**Examples:**

Preview path rewrites without applying them:

```bash
oops-sub-rewrite --dry-run
```

Rewrite all paths non-interactively:

```bash
oops-sub-rewrite --base-dir .third-party --force
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.branch
    :command: main
    :prog_name: oops-sub-branch
    :depth: 2
    :style: table

**Examples:**

Set a default branch for all submodules missing one:

```bash
oops-sub-branch --branch 18.0
```

Skip pull-request submodules during the fix:

```bash
oops-sub-branch --branch 18.0 --skip-pr
```

---

::: mkdocs-click:commands
    :module: oops.commands.submodules.clean
    :command: main
    :prog_name: oops-sub-clean
    :depth: 2
    :style: table

**Examples:**

Remove stale directories and re-init submodules:

```bash
oops-sub-clean
```

Hard-reset the repo before cleaning:

```bash
oops-sub-clean --reset
```
