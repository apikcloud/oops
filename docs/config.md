# Configuration

`oops` reads configuration from YAML files. Two locations are supported and
merged in order — the local file takes precedence over the global one:

| File | Scope |
|---|---|
| `~/.oops.yaml` | Global (user-wide defaults) |
| `.oops.yaml` | Local (per-repository, overrides global) |

Every file must declare a `version` key (currently only `1` is supported).
Unknown keys emit a warning and are ignored.

!!! tip
    Run any command without a config file to get a clear error listing every
    required field that is missing.

## Minimal example

```yaml
version: 1

images:
  source:
    repository: <organization>/<repository>
    file: versions.json

submodules:
  current_path: .third-party
```

## Full reference

### `images`

Controls Odoo image discovery and validation.

```yaml
images:
  source:
    repository: <organization>/<repository>   # required — GitHub repository (owner/repo)
    file: versions.json                       # required — path to the versions file in the repo
  collections:
    - "19.0"
    - "18.0"
    - "17.0"
  release_warn_age_days: 30                   # warn if the current image is older than N days
  registries:
    recommended:
      - <name>
    deprecated:
      - <name>
    warn:
      - <name>
```

| Key | Type | Default | Description |
|---|---|---|---|
| `source.repository` | str | **required** | GitHub `owner/repo` hosting the versions file |
| `source.file` | str | **required** | Path to the JSON versions file inside the repo |
| `collections` | list[str] | `[]` | Odoo version labels to consider (e.g. `"18.0"`) |
| `release_warn_age_days` | int | `30` | Warn when the active image is older than this many days |
| `registries.recommended` | list[str] | `[]` | Registry prefixes considered up-to-date |
| `registries.deprecated` | list[str] | `[]` | Registry prefixes that trigger a deprecation warning |
| `registries.warn` | list[str] | `[]` | Registry prefixes that trigger a generic warning |

---

### `submodules`

Controls how git submodules are organised and validated.

```yaml
submodules:
  current_path: .third-party
  old_paths:
    - third-party
  force_scheme: ssh
  deprecated_repositories:
    OCA/old-repo: OCA/new-repo
  checks:
    - check_path
    - check_branch
    - check_symlink
    - check_url_scheme
    - check_deprecated_repo
    - check_broken_symlink
```

| Key | Type | Default | Description |
|---|---|---|---|
| `current_path` | path | `.third-party` | Expected submodule root directory |
| `old_paths` | list[path] | `[third-party]` | Legacy paths that trigger a migration warning |
| `force_scheme` | str | `ssh` | URL scheme enforced on all submodules (`ssh` or `https`) |
| `deprecated_repositories` | dict | `{}` | Map of `old-repo: new-repo` redirects |
| `checks` | list[str] | *(all)* | Checks to run with `oops-sub-check` (remove entries to skip) |

Available checks: `check_path`, `check_branch`, `check_symlink`,
`check_url_scheme`, `check_deprecated_repo`, `check_broken_symlink`, `check_pr`.

---

### `project`

File-name conventions used by project-level commands.

```yaml
project:
  mandatory_files:
    - requirements.txt
    - odoo_version.txt
    - packages.txt
  recommended_files:
    - README.md
    - CODEOWNERS
    - CHANGELOG.md
    - .gitignore
  file_packages: packages.txt
  file_requirements: requirements.txt
  file_odoo_version: odoo_version.txt
  file_migrate: migrate.sh
  pre_commit_exclude_file: .pre-commit-exclusions
```

| Key | Type | Default | Description |
|---|---|---|---|
| `mandatory_files` | list[str] | `[requirements.txt, odoo_version.txt, packages.txt]` | Files whose absence is reported as an error by `oops-pro-check` |
| `recommended_files` | list[str] | `[README.md, CODEOWNERS, CHANGELOG.md, .gitignore]` | Files whose absence is reported as a warning |
| `file_packages` | str | `packages.txt` | APT packages file |
| `file_requirements` | str | `requirements.txt` | Python requirements file |
| `file_odoo_version` | str | `odoo_version.txt` | File containing the active Odoo version string |
| `file_migrate` | str | `migrate.sh` | Migration script written by `oops-addons-diff --save` and `oops-release-create` |
| `pre_commit_exclude_file` | str | `.pre-commit-exclusions` | Exclusion pattern file written by `oops-pro-exclude` |

---

### `sync`

Source repository for `oops-pro-sync`.

```yaml
sync:
  remote_url: https://github.com/<organization>/<project-template>.git
  branch: main
  files:
    - .pre-commit-config.yaml
    - .github/workflows/ci.yml
```

| Key | Type | Default | Description |
|---|---|---|---|
| `remote_url` | str | `null` | URL of the remote repository to sync from |
| `branch` | str | `null` | Branch to check out in the remote |
| `files` | list[str] | `[]` | Paths to copy from the remote into the local repo |
