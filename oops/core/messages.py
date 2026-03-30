# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: messages.py — oops/core/messages.py

from dataclasses import dataclass


@dataclass
class CommitMessages:
    # Addons
    new_addons: str = "chore: new addons"
    addons_ignored: str = "chore: ignored addons"
    materialize_addons: str = "chore: materialize addon(s) {names}"

    # Submodules
    submodules_rewrite: str = "chore(submodules): rewrite submodule paths to new scheme"
    submodules_prune: str = "chore(submodules): remove unused submodules"
    submodules_rename: str = "chore(submodules): rename submodules to new naming scheme"
    submodules_update: str = (
        "chore(submodules): update submodules to latest upstream versions\n\n{description}"
    )
    submodules_branch: str = "chore(submodules): update .gitmodules with fixed submodule branches"
    submodules_fix_urls: str = "chore(submodules): fix submodule URLs\n\n{description}"
    submodules_replace: str = (
        "chore(submodules): replace submodule(s) and update symlinks\n\n{description}"
    )
    submodule_add: str = """chore(submodules): add submodule {name}"
    
    - url: {url}
    - branch: {branch}
    - path: {path}
    - created symlinks: {symlinks}
    """

    # Miscellaneous
    image_update: str = "chore: update odoo image to '{new}'\n\nFrom '{old}', {days} day(s) newer."
    pre_commit_exclude: str = "chore: update pre-commit exclusions"

    addons_update_table: str = "chore(README): update addons table"
    addons_synchronize: str = (
        "chore: synchronizing the repository based on the list of provided modules"
    )


commit_messages = CommitMessages()
