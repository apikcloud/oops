# Pull Requests

::: oops.commands.pr
    options:
      show_root_heading: false
      show_docstring_modules: true 

---

::: mkdocs-click:commands
    :module: oops.commands.pr.add
    :command: main
    :prog_name: oops pr add
    :depth: 2
    :style: table

**Examples:**

Add a pull request as a submodule from its URL:

```bash
oops pr add https://github.com/OCA/mail/pull/4
```

Pick specific addons non-interactively:

```bash
oops pr add https://github.com/OCA/mail/pull/4 --addons mail_tracking
```

Apply without confirmation prompt (symlink all addons):

```bash
oops pr add https://github.com/OCA/mail/pull/4 --force
```

Stage changes without committing:

```bash
oops pr add https://github.com/OCA/mail/pull/4 --no-commit
```

---

::: mkdocs-click:commands
    :module: oops.commands.pr.manage
    :command: main
    :prog_name: oops pr manage
    :depth: 2
    :style: table

**Examples:**

Interactively promote or demote submodules between pull-request and regular status:

```bash
oops pr manage
```

---

::: mkdocs-click:commands
    :module: oops.commands.pr.show
    :command: main
    :prog_name: oops pr show
    :depth: 2
    :style: table

**Examples:**

List all pull requests across fork submodules:

```bash
oops pr show
```

Output as JSON:

```bash
oops pr show --format json
```

Save JSON output to a file:

```bash
oops pr show --format json --output-path prs.json
```

---

::: mkdocs-click:commands
    :module: oops.commands.pr.replace
    :command: main
    :prog_name: oops pr replace
    :depth: 2
    :style: table

**Examples:**

Replace all PR submodules with their upstream (interactive selection):

```bash
oops pr replace --token $GITHUB_TOKEN
```

Apply without confirmation and skip the commit step:

```bash
oops pr replace --token $GITHUB_TOKEN --force --no-commit
```

Override the target branch (useful when the PR base is `master`):

```bash
oops pr replace --token $GITHUB_TOKEN --branch 17.0
```

---

::: mkdocs-click:commands
    :module: oops.commands.pr.explore
    :command: main
    :prog_name: oops pr explore
    :depth: 2
    :style: table

**Examples:**

List OCA migration PRs for the current project's Odoo version:

```bash
oops pr explore OCA/account
```

List all open PRs (disable the default filter):

```bash
oops pr explore OCA/account --filter ""
```

Filter by an arbitrary title substring as JSON:

```bash
oops pr explore OCA/account --filter sale --format json
```

Target a specific Odoo version explicitly (outside a project):

```bash
oops pr explore OCA/account --version 17.0
```

---

::: mkdocs-click:commands
    :module: oops.commands.pr.check
    :command: main
    :prog_name: oops pr check
    :depth: 2
    :style: table

**Examples:**

Check that no PR-convention submodule points to a closed or merged pull request:

```bash
oops pr check
```

Output as JSON:

```bash
oops pr check --format json
```
