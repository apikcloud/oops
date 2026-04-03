# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: file.py — oops/io/file.py


import contextlib
import logging
import os
import shutil
from collections.abc import Generator
from os import PathLike
from pathlib import Path

from oops.core.models import AddonInfo
from oops.core.paths import PR_DIR, UNPORTED_DIR
from oops.io.manifest import load_manifest
from oops.utils.compat import Optional
from oops.utils.helpers import filter_and_clean
from oops.utils.net import parse_repository_url

# Paths


def ensure_parent(path: Path):
    """Ensure the parent directory of `path` exists."""

    path.parent.mkdir(parents=True, exist_ok=True)


def is_dir_empty(p: Path) -> bool:
    """Return True if the directory exists and is empty."""

    try:
        return p.is_dir() and not any(p.iterdir())
    except FileNotFoundError:
        return False


def relpath(from_path: Path, to_path: Path) -> str:
    """Return a relative path from `from_path` to `to_path`."""

    return os.path.relpath(to_path, start=from_path)


def check_prefix(path: PathLike, prefix: PathLike) -> bool:
    """Check if the given path starts with the given prefix."""

    try:
        p = Path(path).resolve()
        prefix = Path(prefix).resolve()

        return prefix in p.parents or p == prefix
    except FileNotFoundError:
        return False


def is_pull_request_path(raw: Optional[str]) -> bool:
    """Detect if a submodule path looks like a pull request path."""

    if not raw:
        return False

    return raw.startswith(f"{PR_DIR}/") or "pr" in raw.split("/")


# Symlinks


def rewrite_symlink(link: Path, old_prefix: str, new_prefix: str):
    """Rewrite a symlink if its target starts with old prefix."""

    try:
        target = os.readlink(link)
    except OSError:
        return False
    if old_prefix in target:
        new_target = target.replace(old_prefix, new_prefix)
        link.unlink()
        os.symlink(new_target, link)
        return True
    return False


def list_symlinks(path: PathLike, broken_only: bool = False) -> "list[str]":
    """Return a list of all symlink targets under the given path."""

    targets = []
    for root, dirs, files in os.walk(path):
        if ".git" in dirs:
            dirs.remove(".git")
        for n in dirs + files:
            p = Path(root) / n
            if p.is_symlink():
                if broken_only and not p.exists():
                    targets.append(os.readlink(p))
                elif not broken_only:
                    with contextlib.suppress(OSError):
                        targets.append(os.readlink(p))

    return targets


def get_symlink_map(path: str) -> dict:
    """Return a mapping of symlink parent dirs to their target names."""

    # FIXME: assume there is only one symlink per submodule for now
    return {str(Path(t).parent): Path(t).name for t in list_symlinks(path)}


def get_symlink_complete_map(path: str) -> dict:
    res = {}

    for t in list_symlinks(path):
        res.setdefault(str(Path(t).parent), []).append(Path(t).name)

    return res


def materialize_symlink(symlink_path: Path, dry_run: bool) -> None:
    """
    Replace a symbolic link that points to a directory with a physical copy of its target.
    """

    if not symlink_path.exists():
        raise ValueError(f"Path not found: {symlink_path}")
    if not symlink_path.is_symlink():
        raise ValueError(f"Not a symlink: {symlink_path}")

    target = symlink_path.resolve(strict=True)
    if not target.is_dir():
        raise ValueError(f"Symlink target is not a directory: {target}")

    parent = symlink_path.parent
    tmp = parent / f".{symlink_path.name}.__oops_materialize_tmp__"

    if tmp.exists():
        raise ValueError(f"Temporary path already exists: {tmp}")

    logging.debug(f"[oops] materialize: {symlink_path} -> {target}")
    logging.debug(f"[oops] tmp copy:   {tmp}")

    if dry_run:
        return

    try:
        copytree(target, tmp)
        # Remove the symlink and atomically replace with the copied tree
        symlink_path.unlink()
        os.replace(tmp, symlink_path)  # atomic on same filesystem
    except Exception as e:
        # Cleanup tmp on failure
        with contextlib.suppress(Exception):
            if tmp.exists():
                shutil.rmtree(tmp)
        raise ValueError(f"Failed to materialize {symlink_path}: {e}") from e


# Reading/writing files


def parse_text_file(content: str) -> set:
    """Parse Python text file"""

    return filter_and_clean(content.splitlines())


def read_and_parse(path: Path):
    return sorted(parse_text_file(path.read_text()))


def write_text_file(path: Path, lines: list, new_line: str = "\n", add_final_newline: bool = True):
    content = new_line.join(lines)
    if add_final_newline:
        content += new_line
    path.write_text(content)


def copytree(src: Path, dst: Path, ignore_git: bool = True) -> None:
    """
    Copy src tree to dst. Fails if dst exists.
    """

    def _ignore(_dir, names):
        if not ignore_git:
            return set()
        return {n for n in names if n == ".git"}

    shutil.copytree(src, dst, symlinks=True, ignore=_ignore)


def desired_path(
    url: str,
    pull_request: bool = False,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
) -> str:
    """
    Return the desired local path for a git repository URL:
    <prefix>/<owner>/<repo>/<suffix> or <prefix>/PRs/<owner>/<repo>/<suffix>

    If prefix is given, it is prepended to the path.
    If pull_request is True, "PRs/" is inserted after the prefix.
    If suffix is given, it is appended to the path.
    """

    _, owner, repo = parse_repository_url(url)
    if owner == "oca":
        owner = owner.upper()

    parts = [owner, repo]

    if pull_request:
        parts.insert(0, PR_DIR)

    if prefix:
        parts.insert(0, prefix.rstrip("/"))

    if suffix:
        parts.append(suffix)

    return os.path.join(*parts)


# Addons


def find_modified_addons(files: list) -> list:
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
    """Return list of (addon_path, unported) pairs, sorted by path."""
    paths = [(p, False) for p in addons_dir.iterdir()]
    unported = addons_dir / UNPORTED_DIR
    if unported.is_dir():
        paths += [(p, True) for p in unported.iterdir()]
    return sorted(paths, key=lambda x: x[0])


def find_addons(root: Path, shallow: bool = False) -> Generator[AddonInfo, None, None]:
    """Yield all odoo addons under `root`."""

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
            yield AddonInfo.from_path(Path(dirpath), root_path=root, manifest=manifest)

        if shallow:
            depth = len(Path(dirpath).resolve().parts) - len(root_parts)
            if depth >= 1:
                # we're already in a first-level subdir (real or symlink) → don't go deeper
                dirnames[:] = []
