# Release


::: mkdocs-click:commands
    :module: oops.commands.release.prepare
    :command: main
    :prog_name: oops-release-prepare
    :depth: 2
    :style: table

**Examples:**

List modified addons since the last git tag:

```bash
oops-addons-diff tag
```

List modified addons across the last 3 commits:

```bash
oops-addons-diff commit 3
```

Write the migration command to `migrate.sh`:

```bash
oops-addons-diff tag --save
```

---
