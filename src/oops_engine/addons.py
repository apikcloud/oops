# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: addons.py — src/oops_engine/addons.py

import os
from pathlib import Path

from oops_engine.compat import Generator, Optional
from oops_engine.manifest import DEFAULT_MANIFEST_NAMES, load_manifest
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
            if any((parent / name).exists() for name in DEFAULT_MANIFEST_NAMES):
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
        if any(name in filenames for name in DEFAULT_MANIFEST_NAMES):
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
        if any(name in filenames for name in DEFAULT_MANIFEST_NAMES):
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


def dedup_addons_by_path(root: Path, shallow: bool = False) -> "dict[str, Addon]":
    """Discover addons under root, deduplicating by resolved filesystem path.

    os.walk(followlinks=True) (see find_addons) visits both a root-level symlink
    and its resolved target; dotfile directories (e.g. .third-party) sort first,
    so without this the real file wins and active (symlinked) addons get
    miscounted as inactive. Prefers the symlinked entry on collision.

    Args:
        root: Directory to search (forwarded to find_addons).
        shallow: Forwarded to find_addons.

    Returns:
        Mapping of addon.path -> Addon, one entry per unique resolved path.
    """
    seen: "dict[str, Addon]" = {}
    for addon in find_addons(root, shallow=shallow):
        if addon.path not in seen or addon.symlinked:
            seen[addon.path] = addon
    return seen


def enrich_addon_from_subs(
    addon: Addon,
    subs: dict,
    author: Optional[str] = None,
    prefix: Optional[str] = None,
    owner: Optional[str] = None,
) -> None:
    """Enrich addon using a pre-fetched submodule metadata dict.

    Thin convenience wrapper around enrich_addon() that does the
    ``subs.get(addon.rel_path, {})`` lookup callers otherwise repeat.

    Args:
        addon: The addon to enrich, mutated in place.
        subs: rel_path -> metadata dict (from services.git.list_submodules()).
    """
    sub = subs.get(addon.rel_path, {})
    enrich_addon(addon, sub, author=author, prefix=prefix, owner=owner)
