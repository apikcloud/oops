#!/usr/bin/env python3
import ast
import contextlib
import logging
import os
import shutil
from collections.abc import Generator
from os import PathLike
from pathlib import Path

import libcst as cst

from oops.core.config import config
from oops.core.exceptions import NoManifestFound
from oops.core.models import AddonInfo
from oops.utils.compat import Optional, Union
from oops.utils.helpers import filter_and_clean
from oops.utils.net import parse_repository_url


def ensure_parent(path: Path):
    """Ensure the parent directory of `path` exists."""

    path.parent.mkdir(parents=True, exist_ok=True)


def is_dir_empty(p: Path) -> bool:
    """Return True if the directory exists and is empty."""

    try:
        return p.is_dir() and not any(p.iterdir())
    except FileNotFoundError:
        return False


def parse_manifest(filepath: Path) -> dict:
    """
    Parse an Odoo manifest file,
    then safely convert it to a Python dict via ast.literal_eval.
    """
    source = filepath.read_text(encoding="utf-8")

    # Convert the exact dict literal slice to a Python object (safe: literals only).
    manifest = ast.literal_eval(source)
    if not isinstance(manifest, dict):
        logging.error("Parsed manifest is not a dict after literal evaluation.")
        return {}
    return manifest


def load_manifest(addon_dir: Path) -> dict:
    """Return the path to the manifest file in this addon directory."""
    for manifest_name in config.manifest_names:
        manifest_path = addon_dir / manifest_name
        if manifest_path.is_file():
            return parse_manifest(manifest_path)
    logging.error(f"No Odoo manifest found in {addon_dir}")
    return {}


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
        parts.insert(0, "PRs")

    if prefix:
        parts.insert(0, prefix.rstrip("/"))

    if suffix:
        parts.append(suffix)

    return os.path.join(*parts)


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


def check_prefix(path: PathLike, prefix: PathLike) -> bool:
    """Check if the given path starts with the given prefix."""

    try:
        p = Path(path).resolve()
        prefix = Path(prefix).resolve()

        return prefix in p.parents or p == prefix
    except FileNotFoundError:
        return False


def relpath(from_path: Path, to_path: Path) -> str:
    """Return a relative path from `from_path` to `to_path`."""

    return os.path.relpath(to_path, start=from_path)


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


def get_manifest_path(addon_dir: str) -> Optional[str]:
    """Return the path to the manifest file in this addon directory."""
    for manifest_name in config.manifest_names:
        manifest_path = os.path.join(addon_dir, manifest_name)
        if os.path.isfile(manifest_path):
            return manifest_path


def get_manifest_values(path: str, keys: list) -> dict:
    """ Return the elements (keys) of the manifest"""
    result = {}
    manifest = read_manifest(path)
    stmt = manifest.body[0]
    if not isinstance(stmt, cst.SimpleStatementLine):
        return {}

    expr = stmt.body[0]
    if not isinstance(expr, cst.Expr):
        return {}

    if not isinstance(expr.value, cst.Dict):
        return {}

    for element in expr.value.elements:
        if element.key and isinstance(element.key, cst.SimpleString):
            k = element.key.evaluated_value
            if k  in keys and isinstance(element.value, cst.SimpleString):
                result.setdefault(k,element.value.evaluated_value)

    return result


def parse_manifest_cst(raw: str) -> cst.CSTNode:
    return cst.parse_module(raw)


def read_manifest(path: str) -> cst.CSTNode:
    manifest_path = get_manifest_path(path)
    if not manifest_path:
        raise NoManifestFound(f"no Odoo manifest found in {path}")
    with open(manifest_path) as mf:
        return parse_manifest_cst(mf.read())


def find_addons_extended(
    addons_dir: Union[str, Path], installable_only: bool = False, names: Optional[list] = None
):
    """Yield (name, path, manifest) for each addon in the given directory."""

    for name in os.listdir(addons_dir):
        path = os.path.join(addons_dir, name)
        try:
            manifest = parse_manifest(path)
        except NoManifestFound:
            continue
        if installable_only and not manifest.get("installable", True):
            continue

        if names and name not in names:
            continue

        yield name, path, manifest


def find_manifests(path: str, names: Optional[list] = None):
    """Yield the path to each manifest file in the given directory."""

    for name in os.listdir(path):
        addon_path = os.path.join(path, name)
        try:
            manifest_path = get_manifest_path(addon_path)
        except NoManifestFound:
            continue

        if names and name not in names:
            continue

        yield manifest_path


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


def is_pull_request_path(raw: Optional[str]) -> bool:
    """Detect if a submodule path looks like a pull request path."""

    if not raw:
        return False

    return raw.startswith("PRs/") or "pr" in raw.split("/")


def copytree(src: Path, dst: Path, ignore_git: bool = True) -> None:
    """
    Copy src tree to dst. Fails if dst exists.
    """

    def _ignore(_dir, names):
        if not ignore_git:
            return set()
        return {n for n in names if n == ".git"}

    shutil.copytree(src, dst, symlinks=True, ignore=_ignore)


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
