# Misc

Miscellaneous project utilities that don't belong to a specific domain group.

---

::: mkdocs-click:commands
    :module: oops.commands.misc.create_workspace
    :command: main
    :prog_name: oops-misc-create-workspace
    :depth: 2
    :style: table

::: mkdocs-click:commands
    :module: oops.commands.misc.view_doc
    :command: main
    :prog_name: oops-misc-view-doc
    :depth: 2
    :style: table

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `odoo.sources_dir` | *(required)* | Root directory holding one subdirectory per Odoo version |
| `manifest.odoo_version` | *(optional)* | Fallback version when `odoo_version.txt` is absent |

The sources directory must follow this layout (as created by `oops-odoo-download`):

```
<sources_dir>/
└── 17.0/
    ├── community/
    └── enterprise/
```

**Version resolution order:**

1. `odoo_version.txt` at the repository root (parsed Docker image tag → major version)
2. `manifest.odoo_version` in `~/.oops.yaml` (with a warning)
3. Error — the command exits if neither source provides a version

**Examples:**

Generate a workspace file for the current project:

```bash
oops-misc-create-workspace
```

Use a custom sources root (overrides `odoo.sources_dir`):

```bash
oops-misc-create-workspace --base-dir ~/my-odoo-sources
```

Write the workspace file to a specific path:

```bash
oops-misc-create-workspace --output /tmp/review.code-workspace
```

Example output file (`my-project.code-workspace`):

```json
{
    "folders": [
        {
            "path": "."
        }
    ],
    "settings": {
        "python.analysis.extraPaths": [
            "~/odoo-sources/17.0/community",
            "~/odoo-sources/17.0/enterprise"
        ],
        "python.autoComplete.extraPaths": [
            "~/odoo-sources/17.0/community",
            "~/odoo-sources/17.0/enterprise"
        ],
    }
}
```
