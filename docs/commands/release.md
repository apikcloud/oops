# Release

::: mkdocs-click:commands
    :module: oops.commands.release.create
    :command: main
    :prog_name: oops-release-create
    :depth: 2
    :style: table

**Examples:**

Create a minor release (default):

```bash
oops-release-create
```

Create a patch release:

```bash
oops-release-create --fix
```

Set the version explicitly:

```bash
oops-release-create --version v2.0.0
```

Preview what would happen without writing anything:

```bash
oops-release-create --dry-run
```

Commit without creating a tag:

```bash
oops-release-create --no-tag
```

---

::: mkdocs-click:commands
    :module: oops.commands.release.show
    :command: main
    :prog_name: oops-release-show
    :depth: 2
    :style: table

**Examples:**

List all releases with their date, author and commit count:

```bash
oops-release-show
```
