# Miscellaneous

::: oops.commands.misc
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.misc.create_workspace
    :command: main
    :prog_name: oops-misc-create-workspace
    :depth: 2
    :style: table

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

---

::: mkdocs-click:commands
    :module: oops.commands.misc.view_doc
    :command: main
    :prog_name: oops-misc-view-doc
    :depth: 2
    :style: table
