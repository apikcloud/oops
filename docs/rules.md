# Lint Rules

`oops` ships [fixit](https://github.com/Instagram/Fixit) rules for `__manifest__.py` files. They run via
`oops-man-check` (report only) and `oops-man-fix` (apply autofixes).

All rules are in the `oops.rules.manifest` module and are auto-discovered —
no registration needed.

## Rules

| Rule | Autofix | Config key | Description |
|---|---|---|---|
| `ManifestRequiredKeys` | — | `manifest.required_keys` | Reports each key missing from the manifest |
| `OdooManifestAuthorMaintainers` | ✓ (author, version typos) | `manifest.author`, `manifest.odoo_version`, `manifest.allowed_maintainers` | Validates `author`, `maintainers`, `summary`, and `version` format |
| `ManifestNoExtraKeys` | — | `manifest.key_order` | Rejects keys not in the allowed list |
| `ManifestKeyOrder` | ✓ | `manifest.key_order` | Reorders keys to match the canonical order |
| `ManifestVersionBump` | — | `manifest.version_bump_strategy` | Checks that the version is bumped on staged manifests |

## Per-rule details

### `ManifestRequiredKeys`

Reports one violation per missing key. The key list is fully configurable.

### `OdooManifestAuthorMaintainers`

| Check | Autofix | Notes |
|---|---|---|
| `author` value | ✓ | Must equal `manifest.author`; quote style preserved |
| `maintainers` list | — | Must be non-empty; each handle must be in `allowed_maintainers` (if list is non-empty) |
| `summary` non-empty | — | Whitespace-only values are rejected |
| `summary` ≠ `name` | — | Identical values are rejected |
| `version` format | ✓ (typos only) | Pattern is `<odoo_version>.x.y.z` when `odoo_version` is set, otherwise the generic 5-part format. Digit-lookalike typos (`O`→`0`, `l`/`I`→`1`) are autocorrected. Addons from a different Odoo series fall back to the generic check |

### `ManifestNoExtraKeys`

Uses the same list as `key_order` as the allowed set. Add keys to `key_order`
to allow them.

### `ManifestKeyOrder`

Reorders keys in place, preserving comments and trailing commas. Keys not in
`key_order` are sorted alphabetically after all known keys.

!!! note "Two-pass fix"
    When both `ManifestKeyOrder` and `OdooManifestAuthorMaintainers` have
    fixes to apply on the same file, `ManifestKeyOrder` wins the first pass
    (it replaces the whole dict node). Run `oops-man-fix` a second time to
    apply the remaining fixes.

### `ManifestVersionBump`

Git-aware rule — only activates for manifests whose addon has staged files.
Disabled by default; opt in via `manifest.version_bump_strategy` in
`.oops.yaml`.

| Strategy | Behaviour |
|---|---|
| `off` | Rule disabled (default) |
| `strict` | Staged version must exceed the version at `HEAD` — bump on every commit |
| `trunk` | Staged version must exceed the version at the last git tag — one bump per release cycle |

New addons (absent from the reference commit or tag) are always exempt.
Only the last three parts of the version string are compared (`x.y.z` from
`19.0.x.y.z`), so migrating to a new Odoo major version is not a false
positive.

## Adding a rule

See the developer guide at the top of [`oops/rules/manifest.py`](reference/rules/manifest.md)
and the shared helpers in `oops/rules/_helpers.py`.
