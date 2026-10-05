# Project

::: oops.commands.project
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.project.clone
    :command: main
    :prog_name: oops project clone
    :depth: 2
    :style: table

**Examples:**

The repository is cloned into `working_dir/<repo>` as defined in config.
Submodules inside the cloned repository are initialised automatically.

Clone a repository using its full URL:

```bash
oops project clone https://github.com/apikcloud/myproject
```

Clone using an `<org>/<repo>` shorthand:

```bash
oops project clone apikcloud/myproject
```

Clone using a bare repo name (requires `github.owner` in config):

```bash
oops project clone myproject
```

Clone a specific branch:

```bash
oops project clone apikcloud/myproject -b 17.0
```

Clone with more parallel jobs for submodule initialisation:

```bash
oops project clone apikcloud/myproject --jobs 8
```

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
    :module: oops.commands.project.convert
    :command: main
    :prog_name: oops project convert
    :depth: 2
    :style: table

**Examples:**

Bootstrap a repository as an Odoo 19 enterprise project, picking the image closest to a target date:

```bash
oops project convert -v 19 -r 2025-03-15
```

Bootstrap with the most recent available image:

```bash
oops project convert -v 19
```

Bootstrap with the community edition:

```bash
oops project convert -v 18 --no-enterprise
```

Apply without confirmation prompt:

```bash
oops project convert -v 19 --force
```

Stage changes without committing:

```bash
oops project convert -v 19 --no-commit
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
oops project exclude --fail
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

### JSON output

`--format json` emits a fixed envelope, shared with `oops addons list`:

```json
{
  "data": { ... },
  "warnings": ["..."],
  "errors": ["..."],
  "metadata": { "command": "...", "generated_at": "...", ... }
}
```

Every key of `data` is always present; unknown values are `null` (never omitted,
never a display string such as `"—"`).

```json
{
  "project": "my_project",
  "odoo": {
    "version": "15.0",
    "edition": "community",
    "image": { "name": "acme/odoo:15.0-20230103", "registry": "acme/odoo", "release_date": "2023-01-03", "age_days": 1006 },
    "updates": { "available": 12, "latest_release_date": "2025-01-01", "latest_lag_days": 729 }
  },
  "git": {
    "remote_url": "https://github.com/acme/my_project",
    "branch": "main",
    "last_release": "v1.0.0",
    "next_releases": { "fix": "v1.0.1", "minor": "v1.1.0", "major": "v2.0.0" },
    "last_commit": { "sha": "6525df12", "message": "...", "author": "...", "date": "2026-06-25T19:35:55+02:00" }
  },
  "ci": {
    "name": "CI", "status": "completed", "conclusion": "success", "branch": "main",
    "sha": "...", "actor": "...", "event": "push",
    "date": "2026-06-25T17:40:00+00:00", "age_days": 3, "url": "https://github.com/..."
  }
}
```

| Situation | Value |
|---|---|
| Odoo version file missing/unparsable | `odoo.version/edition/image/updates` all `null` (keys kept), error in `errors` |
| Image tag without release date | `image.release_date = null`, `image.age_days = null`, `updates = null` |
| Image registry fetch failed | `updates = null`, message in `warnings` |
| Image up to date | `updates = {"available": 0, "latest_release_date": null, "latest_lag_days": null}` |
| No `origin` remote / unparsable URL | `git.remote_url = null` |
| Detached HEAD | `git.branch = null` |
| No semver tag | `git.last_release = null`, `git.next_releases = null` |
| No commit | `git.last_commit = null` |
| No token, or no run found, or fetch failed | `ci = null` (warning on fetch failure / no run) |

Fatal errors (not a git repository, unexpected exception) are not wrapped: they are
printed as `✘ msg` on stderr with a non-zero exit code.

```bash
oops project show --format json | jq '.data.odoo.version'
oops project show --format json | jq -r '.data.git.branch'
```

!!! warning "Breaking change"
    The former `metrics` member (pre-formatted display rows) is replaced by
    `data.odoo`, `data.git` and `data.ci`.

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
