# ROADMAP

## Purpose

List of improvements or fixes submitted by the user. These items require further consideration before being addressed. They are not ranked by priority; the item number is simply used for reference purposes.  


## Scope

All these items refers to knowledge database and refactor command.

## Items



| Item | Description                                                                                                                                                                                                                                                                                                                                                                                  | Status |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1    | The refactor command must accept multiple modules as parameters, with just one commit per module and a list of the edited files included in the description. Applies the general logic of oops, committing by default with the --no-commit argument. Retains the --no-branch option so that the user has a choice. In the case of multiple add-ons, use a generic branch name.               | Draft  |
| 2    | Remove the three direct CLI entries. Only keep the global build command in misc. The project build must be managed during the refactor using the refresh argument to force a manual rebuild. The project knowledge base should be rebuilt if it is out of date. Furthermore, the list of installed modules should be stored in the repository (define a convention) and include a timestamp. | Draft  |
| 3    | Document all relevant commands in the Google style.                                                                                                                                                                                                                                                                                                                                          | Draft  |
| 4    | Add documentation entries for these commands, take care of API reference too.                                                                                                                                                                                                                                                                                                                | Draft  |
| 5    | Does running `python -m py_compile` on the relevant files before and after refactoring help to secure the process?                                                                                                                                                                                                                                                                           | Draft  |
| 6    | The reformatted files do not adhere to the formatting rules applied during development. We use ruff, which replaces black, for example. At present, this means we have to edit the files and then amend the commit. How can we integrate this into the workflow automatically? Is that possible?                                                                                             | Draft  |

```bash
odoo shell --no-http << EOF
res = env["ir.module.module"].search([("state", "in", ["installed", "to upgrade", "to remove"])]).mapped('name')
print("\n".join(res))
EOF
```
