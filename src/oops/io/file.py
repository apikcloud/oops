# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
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

from __future__ import annotations

import contextlib
import difflib
import logging
import os
import re
import shutil
from collections.abc import Generator
from os import PathLike
from pathlib import Path

import click
from git.repo import Repo
from oops.core.config import config
from oops.core.models import AddonInfo, ImageInfo
from oops.core.paths import PR_DIR, UNPORTED_DIR
from oops.io.manifest import load_manifest
from oops.io.templates import COMPOSE_TEMPLATE, MAILDEV_ENV, MAILDEV_SERVICE, SFTP_SERVICE
from oops.services.docker import parse_image_tag
from oops.services.git import get_submodule_sha
from oops.utils.compat import Optional, Union
from oops.utils.helpers import filter_and_clean
from oops.utils.net import parse_repository_url
from oops.utils.render import human_readable, print_warning

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


def check_prefix(path: str, prefix: str) -> bool:
    """Check whether a path is equal to or descends from a prefix directory.

    Args:
        path: Path to test.
        prefix: Ancestor path to check against.

    Returns:
        True if path equals prefix or is nested inside it, False otherwise.
    """

    try:
        p = Path(path).resolve()
        prefix_path = Path(prefix).resolve()

        return prefix_path in p.parents or p == prefix_path
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


def read_and_parse(path: Path) -> list[str]:
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


def parse_odoo_version(path: Path) -> ImageInfo:
    """Read and parse the Odoo version file into structured image information.

    Reads the first non-empty line of the version file and parses it as a Docker image
    tag, extracting the major version, edition, registry, release date, and flags.

    Args:
        path: Project root directory containing the Odoo version file.

    Returns:
        ImageInfo populated with registry, major version, edition, release date, and flags.

    Raises:
        ValueError: If the version file is empty, missing, or the tag format is unrecognised.
    """
    res = read_and_parse(path / config.project.file_odoo_version)
    if not res:
        raise ValueError()
    return parse_image_tag(res[0])


def get_requirements_diff(requirement_file: Path, repo_path: Path) -> tuple[bool, list, list]:
    """Compare the current requirements file against Python deps declared in addon manifests.

    Collects all ``python`` entries from ``external_dependencies`` across every
    addon found in *repo_path*, sorts them, and runs a line-level diff against
    the existing *requirement_file*.

    Args:
        requirement_file: Path to the existing ``requirements.txt`` (may not exist yet).
        repo_path: Root of the repository to scan for addons.

    Returns:
        A three-element tuple ``(has_changes, new_lines, diff)``:

        - ``has_changes``: True if the new content differs from the current file.
        - ``new_lines``: Sorted list of dependency lines to write.
        - ``diff``: Raw output from :func:`difflib.ndiff`.
    """
    python_dependencies = ["# Requirements generated from manifests external_dependencies:"]
    for addon in find_addons(repo_path, shallow=True):
        python_dependencies.extend(addon.external_dependencies.get("python", []))

    python_dependencies.sort()

    # TODO: duplicate code with parse_requirements, should be refactored
    old_content_list = []
    if requirement_file.exists():
        old_content_list = requirement_file.read_text().splitlines()

    diff = list(difflib.ndiff(old_content_list, python_dependencies))

    has_changes = any(line.startswith(("-", "+")) for line in diff)

    return has_changes, python_dependencies, diff


def file_updater(
    filepath: str,
    new_inner_content: str,
    start_tag: Optional[str] = None,
    end_tag: Optional[str] = None,
    padding: str = "\n",
    append_position: str | bool = "bottom",
    dry_run: bool = False,
) -> bool:
    """Update a file with new content, either replacing the entire file or a section between tags.

    Args:
        filepath: Path to the file to update.
        new_inner_content: New content to insert.
        start_tag: Start tag for targeted replacement (optional).
        end_tag: End tag for targeted replacement (optional).
        padding: Padding to add around the new content (default: newline).
        append_position: Where to insert the tagged block when tags are absent from the file.
            ``'top'`` prepends, ``'bottom'`` appends (default). ``False`` leaves the file
            untouched when tags are missing.

    Returns:
        bool: True if the file was updated, False if no changes have been made.
    """
    path = Path(filepath)
    if not path.exists():
        click.echo(f"File {filepath} does not exist, creating it...")

        if not dry_run:
            os.makedirs(path.parent, exist_ok=True)
            with open(filepath, "w") as new_file:
                if start_tag and end_tag:
                    new_file.write(f"{start_tag}\n{new_inner_content}\n{end_tag}\n")

    if (start_tag and not end_tag) or (end_tag and not start_tag):
        raise ValueError(f"Targeted update for {filepath} requires BOTH start and end tags.")

    content = path.read_text()
    is_to_append = False

    # Case 1: Full File Replacement (missing tags).
    if not start_tag or not end_tag:
        new_file_content = new_inner_content.strip()

    # Case 2: Targeted Replacement (replace content between tags).
    else:
        start_esc = re.escape(start_tag)
        end_esc = re.escape(end_tag)
        # Capture optional leading whitespace to preserve indentation
        pattern = rf"([ \t]*{start_esc}).*?([ \t]*{end_esc})"

        match = re.search(pattern, content, flags=re.DOTALL)
        if match:
            replacement = f"\\1{padding}{new_inner_content}{padding}\\2"
            new_file_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        elif append_position:
            # Content adding if not found.
            new_file_content = f"{start_tag}{padding}{new_inner_content}{padding}{end_tag}"
            is_to_append = True
        else:
            print_warning(f"Tags not found in {filepath} and append_position is False, skipping update.")
            return False

    if new_file_content != content:
        click.echo(f"Updating {filepath}...")
        if dry_run:
            click.echo("[dry-run]: \n" + new_file_content)
            return True

        if is_to_append:
            current_content = path.read_text()
            if append_position == "top":
                new_file_content = f"{new_file_content}\n{current_content}\n"
            else:
                new_file_content = f"{current_content}\n{new_file_content}\n"
            path.write_text(new_file_content)
        else:
            path.write_text(new_file_content + "\n")
        return True

    click.echo(f"No changes detected in {filepath}, skipping update.")
    return False


# ---------------------------------------------------------------------------
# Symlinks
# ---------------------------------------------------------------------------


def list_symlinks(path: PathLike, broken_only: bool = False) -> list[str]:
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


def rewrite_symlink(link: Path, old_prefix: str, new_prefix: str) -> bool:
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


def get_addons_diff(repo: Repo, base_ref: str) -> tuple[list, list, list]:
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
        f for f in repo.git.diff("--name-only", "--diff-filter=D", base_ref, "HEAD").splitlines() if "/" not in f
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
    template: str = "#!/bin/bash\n\n# [{release}] migration script\n{body}\n"
    commands = []

    if removed_addons:
        commands.append(remove_command.format(addons=",".join(sorted(removed_addons))))
    if new_addons:
        commands.append(install_command.format(addons=",".join(sorted(new_addons))))
    if updated_addons:
        commands.append(update_command.format(addons=",".join(sorted(updated_addons))))

    return template.format(body="\n".join(commands), release=release or "Unreleased")


def write_migration_script(content: str, dry_run: bool = False) -> Optional[str]:
    """Write a migration script to the configured file path and mark it executable.

    Args:
        content: Full script content to write.
        dry_run: If True, print to stdout instead of writing to disk. Defaults to False.
    """
    import click  # noqa: PLC0415

    if dry_run:
        click.echo(content)
        return None

    with open(config.project.file_migrate, mode="w", encoding="UTF-8") as file:
        file.write(content)

    # Do a chmod +x
    st = os.stat(config.project.file_migrate)
    os.chmod(config.project.file_migrate, st.st_mode | 0o111)

    return config.project.file_migrate


def update_gitignore(  # noqa: C901
    file_path: Union[str, Path],
    folders: list,
    header: str = "# Ignored addons (auto)",
) -> bool:
    """Ensure given folder names are present in .gitignore under a header section.

    Adds missing entries only (idempotent). Normalizes folder patterns to 'name/'.
    Appends a header at EOF if absent, then the new folders under it.

    Args:
        file_path: Path to .gitignore file
        folders: List of folder names to add
        header: Header comment to use for the section

    Returns:
        True if the file was modified, False otherwise
    """
    p = Path(file_path)
    lines: list[str] = []

    if p.exists():
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

    # Normalize target patterns to directory form 'name/'
    def canon(s: str) -> str:
        base = s.strip().strip("/").lstrip("./")
        return f"{base}/" if base else ""

    wanted = sorted({canon(f) for f in folders if canon(f)})

    if not wanted:
        return False

    # Collect existing patterns (treat 'foo' and 'foo/' as duplicates)
    existing = set()
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        existing.add(s.rstrip("/"))

    missing = [w for w in wanted if w.rstrip("/") not in existing]

    if not missing:
        return False

    # Find or create header location
    header_line = header.strip()
    try:
        idx = next(i for i, line in enumerate(lines) if line.strip() == header_line)
        insert_at = idx + 1
        block = []
        # Add a blank line after header if not already
        if insert_at >= len(lines) or lines[insert_at].strip():
            block.append("\n")
        block += [f"{m}\n" for m in missing]
        lines[insert_at:insert_at] = block
    except StopIteration:
        # Ensure file ends with a newline
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        # Append header + entries at EOF
        tail = []
        if lines and lines[-1].strip():
            tail.append("\n")
        tail.append(f"{header_line}\n")
        tail += [f"{m}\n" for m in missing]
        lines.extend(tail)

    p.write_text(human_readable(lines), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------


def build_compose(
    image: str,
    port: int,
    prefix: str,
    dev: bool,
    with_maildev: bool,
    with_sftp: bool,
) -> str:
    """Render a docker-compose.yml file from the project template.

    Args:
        image: Full Docker image reference for the Odoo service (e.g. ``registry/odoo:17.0``).
        port: Host port to map to Odoo's internal port 8069.
        prefix: Docker-safe volume name prefix, typically derived from the repo name.
        dev: Whether to append ``--dev=all`` to the Odoo command.
        with_maildev: Include the maildev SMTP catch-all service.
        with_sftp: Include the SFTP service.

    Returns:
        Rendered docker-compose.yml content as a string, ready to write to disk.
    """
    return COMPOSE_TEMPLATE.format(
        image=image,
        port=port,
        prefix=prefix,
        dev_flag="" if not dev else " --dev=all",
        maildev_env=MAILDEV_ENV if with_maildev else "",
        maildev_service=MAILDEV_SERVICE if with_maildev else "",
        sftp_service=SFTP_SERVICE if with_sftp else "",
    )


def volume_prefix(repo_path: Path) -> str:
    """Derive a Docker-safe volume prefix from the repo directory name.

    Strips a leading ``odoo-`` prefix (common convention) then
    replaces any non-alphanumeric character with an underscore.

    Examples:
        ``odoo-my-project`` → ``my_project``
        ``my-project``      → ``my_project``
        ``odoo-client_v2``  → ``client_v2``
    """
    name = repo_path.name
    if name.startswith("odoo-"):
        name = name[len("odoo-") :]
    return re.sub(r"[^a-z0-9]", "_", name.lower())
