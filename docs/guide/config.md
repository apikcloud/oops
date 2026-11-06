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
| `checks` | list[str] | *(all)* | Checks to run with `oops submodules check` (remove entries to skip) |

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
| `mandatory_files` | list[str] | `[requirements.txt, odoo_version.txt, packages.txt]` | Files whose absence is reported as an error by `oops project check` |
| `recommended_files` | list[str] | `[README.md, CODEOWNERS, CHANGELOG.md, .gitignore]` | Files whose absence is reported as a warning |
| `file_packages` | str | `packages.txt` | APT packages file |
| `file_requirements` | str | `requirements.txt` | Python requirements file |
| `file_odoo_version` | str | `odoo_version.txt` | File containing the active Odoo version string |
| `file_migrate` | str | `migrate.sh` | Migration script written by `oops addons diff --save` and `oops release create` |
| `pre_commit_exclude_file` | str | `.pre-commit-exclusions` | Exclusion pattern file written by `oops project exclude` |

---

### `classification`

Optional. Forces the class of specific addons (`custom`, `oca` or `third-party`), for cases the automatic detection cannot infer, such as a family of addons with a legacy prefix or addons without any prefix.

```yaml
classification:
  custom:
    - "legacy_*"
    - unprefixed_addon
  third-party:
    - acme_vendored_addon
```

Without this section, addons are classified automatically, in this order:

1. `(OCA)` in the manifest author: `oca`
2. Manifest author equal to `manifest.author`: `custom`
3. Technical name starting with `project.prefix`: `custom`
4. Submodule owned by `OCA`: `oca`, or by `github.owner`: `custom`
5. Otherwise: `third-party`

Rules of this section run first and override all of the above.

| Key | Type | Default | Description |
|---|---|---|---|
| `custom` | list[str] | `[]` | Addons forced to `custom` |
| `oca` | list[str] | `[]` | Addons forced to `oca` |
| `third-party` | list[str] | `[]` | Addons forced to `third-party` |

Each entry is an exact technical name or a glob (`*`, `?`, `[seq]`), matched case-sensitively against the whole name: `sale` does not match `sale_management`, use `sale*` for that.

An exact name beats any glob, which allows exceptions to a family of addons. If an addon matches several classes at the same level, the command fails instead of picking one. The same entry in two classes is rejected when the configuration is loaded.

As `classification` is a mapping, a local `.oops.yaml` section replaces the global one entirely.

!!! note "Project KB"
    The KB stores the class of each addon and does not track this section. After changing it, rebuild the KB with `oops addons analyze --refresh`.

---

### `sync`

Source repository for `oops project sync`.

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

---

### `manifest`

Controls lint rules applied by `oops-check-manifest` and `oops-fix-manifest` to
`__manifest__.py` files.

```yaml
manifest:
  author: AAcmek                        # required — expected value for the 'author' field
  odoo_version: "19.0"                  # optional — enforces version prefix (e.g. 19.0.x.y.z)
  version_bump_strategy: trunk          # optional — version bump check strategy (default: off)
  allowed_maintainers:
    - alice
    - bob
  required_keys:
    - name
    - version
    - summary
    - website
    - author
    - maintainers
    - depends
    - data
    - license
    - auto_install
    - installable
  key_order:
    - name
    - summary
    - version
    - category
    - author
    - maintainers
    - website
    - depends
    - data
    - assets
    - demo
    - application
    - auto_install
    - installable
    - license
```

| Key | Type | Default | Description |
|---|---|---|---|
| `author` | str | **required** | Expected value for the manifest `author` field; autofixed by `oops-fix-manifest` |
| `odoo_version` | str | `null` | When set, enforces the version prefix (e.g. `"19.0"` → `19.0.x.y.z`). Addons from another series are validated against the generic 5-part pattern |
| `version_bump_strategy` | str | `off` | When to require a version bump on staged manifests: `off` (disabled), `strict` (every commit), `trunk` (once per release, relative to last tag) |
| `allowed_maintainers` | list[str] | `[]` | GitHub handles accepted in the `maintainers` list; empty list disables the check |
| `required_keys` | list[str] | *(see above)* | Keys that must be present in every manifest; reported individually if missing |
| `key_order` | list[str] | *(see above)* | Canonical key order enforced by `ManifestKeyOrder`; also used as the allowed-key list by `ManifestNoExtraKeys` |

!!! note "version_bump_strategy"
    `strict` enforces a bump on every commit that touches an addon — suitable
    for granular per-commit changelogs. `trunk` only requires the version to
    exceed the last git tag — better for squash/rebase workflows where a single
    bump per release cycle is enough.
