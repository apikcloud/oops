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
