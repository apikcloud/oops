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
        ]
    }
}
```

---

::: mkdocs-click:commands
    :module: oops.commands.misc.edit_config
    :command: main
    :prog_name: oops-misc-edit-config
    :depth: 2
    :style: table

**Examples:**

Open the global config in the default editor:

```bash
oops-misc-edit-config
```

Open the local project config instead:

```bash
oops-misc-edit-config --local
```

---

::: mkdocs-click:commands
    :module: oops.commands.misc.new_project
    :command: main
    :prog_name: oops-misc-new-project
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command requires `gh` to be authenticated (`gh auth login`) and a
    `github` section in `~/.oops.yaml`. Behaviour may change in future releases.

**Configuration (`~/.oops.yaml`):**

```yaml
github:
  template: "apikcloud/odoo-repository-template"
  owner: "apikcloud"
  visibility: "private"
  prefix: "odoo"
  team: "developers"
  action_repo: "apikcloud/workflows"
  action_workflow: "update.yml"
  action_inputs:
    branch: "main"
    update: false
```

**Examples:**

Create a new project (prompts for name, slugifies, confirms):

```bash
oops-misc-new-project
```

Create without cloning locally:

```bash
oops-misc-new-project --no-clone
```

---

::: mkdocs-click:commands
    :module: oops.commands.misc.usage
    :command: main
    :prog_name: oops-misc-usage
    :depth: 2
    :style: table

**Examples:**

Show per-command invocation counts:

```bash
oops-misc-usage
```

---

::: mkdocs-click:commands
    :module: oops.commands.misc.view_doc
    :command: main
    :prog_name: oops-misc-view-doc
    :depth: 2
    :style: table
