# Quickstart

## Install

```bash
uv tool install git+https://github.com/apikcloud/oops.git@{oops_version}
```

(The `{oops_version}` placeholder is replaced with the installed version at build time — see [Home](../index.md).)

## Initialise an existing project

You have just cloned an Odoo multi-repository project locally. Set up the
working tree (sync submodules, materialize symlinks, generate the addon table):

```bash
oops project init
```

## Next steps

- Browse the per-group [Commands](commands/addons.md) reference to see what
  `oops` can do.
- Configure global defaults by editing `~/.oops.yaml` — see
  [Configuration](config.md).
- Wire `oops` into your repo's pre-commit chain — see [Hooks](hooks.md).
