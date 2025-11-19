from dataclasses import dataclass


@dataclass
class CommitMessages:
    # Addons
    new_addons: str = "chore: new addons"
    addons_ignored: str = "chore: ignored addons"
    materialize_addons: str = "chore: materialize addon(s) {names}"

    # Submodules
    submodules_rewrite: str = "chore: rewrite submodule paths based on remote URL"
    submodules_prune: str = "chore: remove unused submodules"
    submodules_rename: str = "chore: rename submodules to new naming scheme"
    submodules_update: str = "chore: update submodules to latest upstream versions"
    submodule_add: str = "chore: add submodule {name}"
    submodule_add_desc: str = """
    - url: {url}
    - branch: {branch}
    - path: {path}
    - created symlinks: {symlinks}
    """

    # Miscellaneous
    image_update: str = "chore: update odoo image to '{new}'\n\nFrom '{old}', {days} day(s) newer."
    pre_commit_exclude: str = "chore: update pre-commit exclusions"


commit_messages = CommitMessages()
