# Use cases

!!! warning "Draft"
    This section is incomplete. Additional use cases will be added over time.

## Migrate pull-request submodules to the canonical layout

When submodules tracking open pull requests were added without the `--pull-request`
flag, they end up with a generic name and path. This workflow brings them in line
with the expected layout under `.third-party/PRs/`.

**Step 1** — Mark and rename the affected submodules:

```bash
oops submodules rename --pull-request sub_1 sub_2
```

This reads the submodule URL, detects the PR context, and renames each entry
in `.gitmodules` to the `PRs/<ORG>/<REPO>/<ADDON>` convention.

**Step 2** — Move them to the correct path:

```bash
oops submodules rewrite --force
```

This relocates the submodule directories under `.third-party/` and rewrites
all symlinks that pointed to the old paths.
