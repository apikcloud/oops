# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: addons.py — src/oops_engine/addons.py

import os
from pathlib import Path

from oops_engine.compat import Generator, Optional
from oops_engine.manifest import load_manifest
from oops_engine.models import Addon
from oops_engine.paths import PR_DIR, UNPORTED_DIR
from oops_engine.provenance import classify_addon


def find_modified_addons(files: list) -> list:
    """Return the names of addons containing any of the given file paths.

    Walks up each file path until a directory with an Odoo manifest is found.

    Args:
        files: List of file paths to inspect.

    Returns:
        Sorted list of addon directory names that contain at least one of the files.
    """
    addons = set()
    for f in files:
        p = Path(f)
        # Go back up the tree until you find a manifest
        for parent in [p] + list(p.parents):
            if (parent / "__manifest__.py").exists() or (parent / "__openerp__.py").exists():
                addons.add(str(parent.name))
                break
    return sorted(addons)


def collect_addon_paths(addons_dir: Path) -> list:
    """Collect (addon_path, unported) pairs from an addons directory.

    Args:
        addons_dir: Root addons directory to inspect.

    Returns:
        Sorted list of (Path, bool) pairs where the bool indicates
        whether the addon lives under the unported subdirectory.
    """
    paths = [(p, False) for p in addons_dir.iterdir()]
    unported = addons_dir / UNPORTED_DIR
    if unported.is_dir():
        paths += [(p, True) for p in unported.iterdir()]
    return sorted(paths, key=lambda x: x[0])


def find_addons(root: Path, shallow: bool = False) -> Generator[Addon, None, None]:
    """Yield Addon for every Odoo addon found under a root directory.

    Args:
        root: Directory to search recursively (symlinked first-level dirs are followed).
        shallow: If True, do not recurse deeper than one level into subdirectories.
            Defaults to False.

    Yields:
        Addon for each addon directory containing a manifest file.
    """

    root_parts = root.resolve().parts

    # followlinks=True lets us enter first-level *symlinked* directories
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        # skip VCS noise
        if ".git" in dirnames:
            dirnames.remove(".git")

        if "setup" in dirnames:
            dirnames.remove("setup")  # don't enter setup/ subdir

        # found an addon here?
        if "__manifest__.py" in filenames or "__openerp__.py" in filenames:
            manifest = load_manifest(Path(dirpath))
            yield Addon.from_path(Path(dirpath), root_path=root, manifest=manifest)

        if shallow:
            depth = len(Path(dirpath).resolve().parts) - len(root_parts)
            if depth >= 1:
                # we're already in a first-level subdir (real or symlink) → don't go deeper
                dirnames[:] = []


def find_addon_dirs(root: Path, with_pr: bool = False) -> list:
    """Return all addon directories found under a root path.

    Args:
        root: Directory to search recursively.
        with_pr: If True, descend into pull-request subdirectories. Defaults to False.

    Returns:
        List of Path objects for each directory containing a manifest file.
    """
    addons = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        if not with_pr and PR_DIR in dirnames:
            dirnames.remove(PR_DIR)
        if "__manifest__.py" in filenames or "__openerp__.py" in filenames:
            addons.append(Path(dirpath))
    return addons


def enrich_addon(
    addon: Addon, sub: dict, author: Optional[str] = None, prefix: Optional[str] = None, owner: Optional[str] = None
) -> None:
    """Populate git-state and classification fields on an Addon.

    Args:
        addon: The addon to enrich, mutated in place.
        sub: Submodule metadata dict for this addon's rel_path (from list_submodules),
            or an empty dict if the addon is not inside a submodule.
    """
    addon.submodule = sub.get("name", "")
    addon.branch = sub.get("branch", "")
    addon.pull_request = sub.get("pr", False)

    submodule_org = addon.submodule.split("/")[0] if addon.submodule else ""
    addon.classification = classify_addon(
        addon.author,
        addon.technical_name,
        submodule_org,
        project_author=author,
        project_prefix=prefix,
        github_owner=owner,
    )
