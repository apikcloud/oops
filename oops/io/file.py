# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: file.py — oops/io/file.py

"""
Filesystem helpers for path manipulation, file I/O, symlink management, and addon discovery.

Sections:
    - Path utilities: path predicates, canonical path computation, prefix checks
    - File I/O: plain-text file reading/writing and directory copy
    - Symlinks: listing, mapping, rewriting, and materialising symlinks
    - Addons: locating and collecting Odoo addon directories
"""

import contextlib
import logging
import os
import shutil
from collections.abc import Generator
from os import PathLike
from pathlib import Path

from git.repo import Repo

from oops.core.config import config
from oops.core.models import AddonInfo
from oops.core.paths import PR_DIR, UNPORTED_DIR
from oops.io.manifest import load_manifest
from oops.services.git import get_submodule_sha
from oops.utils.compat import Optional
from oops.utils.helpers import filter_and_clean
from oops.utils.net import parse_repository_url

# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------


def ensure_parent(path: Path):
    """Ensure the parent directory of a path exists, creating it if needed.

    Args:
        path: Path whose parent directory should be created.
    """

    path.parent.mkdir(parents=True, exist_ok=True)


def is_dir_empty(p: Path) -> bool:
    """Check whether a directory exists and contains no entries.

    Args:
        p: Path to the directory to check.

    Returns:
        True if the directory exists and is empty, False otherwise.
    """

    try:
        return p.is_dir() and not any(p.iterdir())
    except FileNotFoundError:
        return False


def relpath(from_path: Path, to_path: Path) -> str:
    """Compute a relative path from one location to another.

    Args:
        from_path: The starting directory.
        to_path: The target path to reach.

    Returns:
        Relative path string from from_path to to_path.
    """

    return os.path.relpath(to_path, start=from_path)


def check_prefix(path: PathLike, prefix: PathLike) -> bool:
    """Check whether a path is equal to or descends from a prefix directory.

    Args:
        path: Path to test.
        prefix: Ancestor path to check against.

    Returns:
        True if path equals prefix or is nested inside it, False otherwise.
    """

    try:
        p = Path(path).resolve()
        prefix = Path(prefix).resolve()

        return prefix in p.parents or p == prefix
    except FileNotFoundError:
        return False


def is_pull_request_path(raw: Optional[str]) -> bool:
    """Detect whether a submodule path looks like a pull request path.

    Args:
        raw: Submodule path string to inspect.

    Returns:
        True if the path matches pull-request naming conventions, False otherwise.
    """

    if not raw:
        return False

    return raw.startswith(f"{PR_DIR}/") or "pr" in raw.split("/")


def desired_path(
    url: str,
    pull_request: bool = False,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
) -> str:
    """Build the desired local path for a git repository URL.

    Produces `<prefix>/<owner>/<repo>/<suffix>`, inserting a pull-request
    segment after the prefix when pull_request is True.

    Args:
        url: GitHub repository URL (HTTPS or SSH).
        pull_request: If True, insert the pull-request directory segment. Defaults to False.
        prefix: Optional path prefix prepended before the owner segment.
        suffix: Optional path segment appended after the repo name.

    Returns:
        Relative filesystem path derived from the repository URL components.
    """

    _, owner, repo = parse_repository_url(url)
    if owner == "oca":
        owner = owner.upper()

    parts = [owner, repo]

    if pull_request:
        parts.insert(0, config.pull_request_dir)

    if prefix:
        parts.insert(0, prefix.rstrip("/"))

    if suffix:
        parts.append(suffix)

    return os.path.join(*parts)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def parse_text_file(content: str) -> set:
    """Parse a text file's content into a set of non-empty, stripped lines.

    Args:
        content: Raw file content as a string.

    Returns:
        Set of cleaned, non-empty lines.
    """

    return filter_and_clean(content.splitlines())


def read_and_parse(path: Path):
    """Read a text file and return its non-empty, sorted lines.

    Args:
        path: Path to the text file to read.

    Returns:
        Sorted list of cleaned, non-empty lines from the file.
    """
    return sorted(parse_text_file(path.read_text()))


def write_text_file(path: Path, lines: list, new_line: str = "\n", add_final_newline: bool = True):
    """Write a list of lines to a text file.

    Args:
        path: Destination file path.
        lines: Lines to write, joined by new_line.
        new_line: Line separator. Defaults to "\\n".
        add_final_newline: If True, append a trailing newline. Defaults to True.
    """
    content = new_line.join(lines)
    if add_final_newline:
        content += new_line
    path.write_text(content)


def copytree(src: Path, dst: Path, ignore_git: bool = True) -> None:
    """Copy a directory tree from src to dst, preserving symlinks.

    Args:
        src: Source directory to copy.
        dst: Destination path, must not already exist.
        ignore_git: If True, skip .git directories. Defaults to True.
    """

    def _ignore(_dir, names):
        if not ignore_git:
            return set()
        return {n for n in names if n == ".git"}

    shutil.copytree(src, dst, symlinks=True, ignore=_ignore)


def parse_packages(path: Path) -> list:
    """Read and return the sorted list of packages from the project packages file.

    Args:
        path: Project root directory containing the packages file.

    Returns:
        Sorted list of package names.
    """
    return read_and_parse(path / config.project.file_packages)


def parse_requirements(path: Path) -> list:
    """Read and return the sorted list of entries from the project requirements file.

    Args:
        path: Project root directory containing the requirements file.

    Returns:
        Sorted list of requirement strings.
    """
    return read_and_parse(path / config.project.file_requirements)


def parse_odoo_version(path: Path) -> str:
    """Read and return the Odoo version string from the project version file.

    Args:
        path: Project root directory containing the Odoo version file.

    Returns:
        Odoo version string (first non-empty line of the version file).

    Raises:
        ValueError: If the version file is empty or missing.
    """
    res = read_and_parse(path / config.project.file_odoo_version)
    if not res:
        raise ValueError()
    return res[0]


# ---------------------------------------------------------------------------
# Symlinks
# ---------------------------------------------------------------------------


def list_symlinks(path: PathLike, broken_only: bool = False) -> "list[str]":
    """Collect symlink targets found recursively under a directory.

    Args:
        path: Root directory to walk.
        broken_only: If True, only return targets of broken symlinks. Defaults to False.

    Returns:
        List of symlink target strings found under path.
    """

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
    """Build a mapping of symlink parent directories to their single target name.

    Args:
        path: Root directory to scan for symlinks.

    Returns:
        Dict mapping each parent directory path to one target name.
        Assumes at most one symlink per parent directory.
    """

    # FIXME: assume there is only one symlink per submodule for now
    return {str(Path(t).parent): Path(t).name for t in list_symlinks(Path(path))}


def get_symlink_complete_map(path: str) -> dict:
    """Return a mapping of symlink parent dirs to all their target names.

    Args:
        path: Root directory to scan for symlinks.

    Returns:
        Dict mapping each parent directory path to a list of target names
        found under it.
    """
    res = {}

    for t in list_symlinks(Path(path)):
        res.setdefault(str(Path(t).parent), []).append(Path(t).name)

    return res


def rewrite_symlink(link: Path, old_prefix: str, new_prefix: str):
    """Rewrite a symlink's target by replacing a path prefix.

    Args:
        link: Path to the symlink to rewrite.
        old_prefix: Prefix to replace in the symlink target.
        new_prefix: Replacement prefix.

    Returns:
        True if the symlink was rewritten, False if the target did not match.
    """

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


def materialize_symlink(symlink_path: Path, dry_run: bool) -> None:
    """Replace a symlink pointing to a directory with a physical copy of its target.

    Args:
        symlink_path: Path to the symlink to materialize.
        dry_run: If True, validate inputs but make no filesystem changes.

    Raises:
        ValueError: If the path does not exist, is not a symlink, its target
            is not a directory, or materialization fails.
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


# ---------------------------------------------------------------------------
# Addons
# ---------------------------------------------------------------------------


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


def find_addons(root: Path, shallow: bool = False) -> Generator[AddonInfo, None, None]:
    """Yield AddonInfo for every Odoo addon found under a root directory.

    Args:
        root: Directory to search recursively (symlinked first-level dirs are followed).
        shallow: If True, do not recurse deeper than one level into subdirectories.
            Defaults to False.

    Yields:
        AddonInfo for each addon directory containing a manifest file.
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
            yield AddonInfo.from_path(Path(dirpath), root_path=root, manifest=manifest)

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


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def get_addons_diff(repo: Repo, base_ref: str) -> "tuple[list, list, list]":
    """Classify addon changes between base_ref and HEAD into new, updated, and removed.

    Args:
        repo: GitPython Repo object for the local repository.
        base_ref: Git ref (tag, branch, or commit-ish) to compare against HEAD.

    Returns:
        Tuple of (new_addons, updated_addons, removed_addons), each a sorted list
        of addon names.
    """
    # Newly added root-level entries (new symlinks or addon folders)
    added_files = repo.git.diff("--name-only", "--diff-filter=A", base_ref, "HEAD").splitlines()
    new_addons = set(find_modified_addons(added_files))

    # Removed root-level entries: verify each had a manifest at base_ref
    deleted_root = [
        f
        for f in repo.git.diff("--name-only", "--diff-filter=D", base_ref, "HEAD").splitlines()
        if "/" not in f
    ]
    removed_addons = []
    for name in deleted_root:
        try:
            repo.git.show(f"{base_ref}:{name}/__manifest__.py")
            removed_addons.append(name)
        except Exception:
            pass
    removed_addons = sorted(removed_addons)

    # All changed files across the main repo and submodules
    diff_files = repo.git.diff("--name-only", base_ref, "HEAD").splitlines()
    for sm in repo.submodules:
        subrepo = sm.module()

        old_sha = get_submodule_sha(repo, base_ref, str(sm.path))
        new_sha = get_submodule_sha(repo, "HEAD", str(sm.path))

        # The submodule has not changed between base_ref and HEAD.
        if not old_sha or not new_sha or old_sha == new_sha:
            continue

        sub_diff = subrepo.git.diff("--name-only", old_sha, new_sha).splitlines()
        diff_files.extend(f"{sm.path}/{f}" for f in sub_diff)

    all_addons = set(find_modified_addons(diff_files))
    updated_addons = all_addons - new_addons

    return sorted(new_addons), sorted(updated_addons), sorted(removed_addons)


def make_migration_command(
    new_addons: Optional[list] = None,
    updated_addons: Optional[list] = None,
    removed_addons: Optional[list] = None,
    release: Optional[str] = None,
) -> str:
    """Build the content of a migration shell script from addon change lists.

    Args:
        new_addons: Addons to install with ``-i``.
        updated_addons: Addons to update with ``-u``.
        removed_addons: Addons that were removed; included as a comment only.
        release: Release label used in the script header. Defaults to "Unreleased".

    Returns:
        Full migration script content as a string, including the shebang line.
    """
    remove_command = "# Removed addons (manual action required): {addons}"
    install_command = "odoo --stop-after-init --no-http -i {addons}"
    update_command = "odoo --stop-after-init --no-http -u {addons}"
    template: str = "#!/bin/bash\n\n# {release} migration script\n{body}\n"
    commands = []

    if removed_addons:
        commands.append(remove_command.format(addons=",".join(sorted(removed_addons))))
    if new_addons:
        commands.append(install_command.format(addons=",".join(sorted(new_addons))))
    if updated_addons:
        commands.append(update_command.format(addons=",".join(sorted(updated_addons))))

    return template.format(body="\n".join(commands), release=release or "Unreleased")


def write_migration_script(content: str, dry_run: bool = False) -> None:
    """Write a migration script to the configured file path and mark it executable.

    Args:
        content: Full script content to write.
        dry_run: If True, print to stdout instead of writing to disk. Defaults to False.
    """
    import click  # noqa: PLC0415

    if dry_run:
        click.echo(content)
        return

    with open(config.project.file_migrate, mode="w", encoding="UTF-8") as file:
        file.write(content)

    # Do a chmod +x
    st = os.stat(config.project.file_migrate)
    os.chmod(config.project.file_migrate, st.st_mode | 0o111)
