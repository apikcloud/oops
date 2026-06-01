# Depends

::: oops.commands.depends
    options:
      show_root_heading: false
      show_docstring_modules: true

---

::: mkdocs-click:commands
    :module: oops.commands.depends.show
    :command: main
    :prog_name: oops depends show
    :depth: 2
    :style: table

**Examples:**

Generate an HTML dependency report for the current project (opens in browser):

```bash
oops depends show
```

Write the HTML report to a specific path:

```bash
oops depends show --output /tmp/deps.html
```

Export the dependency graph as JSON:

```bash
oops depends show --format json
```

Write the JSON output to a file:

```bash
oops depends show --format json --output deps.json
```

---

::: mkdocs-click:commands
    :module: oops.commands.depends.check
    :command: main
    :prog_name: oops depends check
    :depth: 2
    :style: table

!!! warning "Not yet implemented"
    `oops depends check` is declared but not yet implemented. Running it will raise `NotImplementedError`.
