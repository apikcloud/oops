# Addons

::: mkdocs-click:commands
    :module: oops.commands.addons.add
    :command: main
    :prog_name: oops-addons-add
    :depth: 2
    :style: table

**Examples:**

Add `mass_editing` and `web_notify` from any tracked submodule:

```bash
oops-addons-add mass_editing,web_notify
```

Stage the symlinks without committing:

```bash
oops-addons-add sale_management --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.compare
    :command: main
    :prog_name: oops-addons-compare
    :depth: 2
    :style: table

**Examples:**

Check which addons from a list are missing or extra in the repo root:

```bash
oops-addons-compare "sale,purchase,account"
```

Remove extra local symlinks not in the provided list:

```bash
oops-addons-compare "sale,purchase" --delete
```

Compare against a file and skip the commit:

```bash
oops-addons-compare "$(cat addons.txt)" --delete --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.download
    :command: main
    :prog_name: oops-addons-download
    :depth: 2
    :style: table

**Examples:**

Download all addons from a branch:

```bash
oops-addons-download https://github.com/OCA/server-ux.git 18.0
```

Download only specific addons:

```bash
oops-addons-download https://github.com/OCA/server-ux.git 18.0 --addons mass_editing
```

Use a GitHub token for private repositories:

```bash
oops-addons-download https://github.com/OCA/server-ux.git 18.0 --token $GH_TOKEN
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.list
    :command: main
    :prog_name: oops-addons-list
    :depth: 2
    :style: table

**Examples:**

Display the addon table:

```bash
oops-addons-list
```

Export as JSON for scripting:

```bash
oops-addons-list --format json
```

Limit to a single submodule:

```bash
oops-addons-list -n apikcloud/apik-addons
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.materialize
    :command: main
    :prog_name: oops-addons-materialize
    :depth: 2
    :style: table

**Examples:**

Preview what would be copied without making changes:

```bash
oops-addons-materialize my_addon --dry-run
```

Replace a symlink with a real directory and commit:

```bash
oops-addons-materialize my_addon
```

---

::: mkdocs-click:commands
    :module: oops.commands.addons.diff
    :command: main
    :prog_name: oops-addons-diff
    :depth: 2
    :style: table

**Examples:**

Show modified addons since the latest tag:

```bash
oops-addons-diff
```

Compare against a specific tag:

```bash
oops-addons-diff --tag v1.2.0
```

Compare against the last 5 commits:

```bash
oops-addons-diff --commits 5
```

Write the migration script to `migrate.sh` and commit:

```bash
oops-addons-diff --save
```

Write the migration script without committing:

```bash
oops-addons-diff --save --no-commit
```
