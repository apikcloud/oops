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
import os
import re
import shutil
from os import PathLike
from pathlib import Path

import click
from git.repo import Repo
from oops.core.config import config
from oops.core.exceptions import ConfigError, OopsError
from oops.core.logger import log
from oops.core.models import ImageInfo
from oops.core.paths import PR_DIR
from oops.io.templates import COMPOSE_TEMPLATE, MAILDEV_ENV, MAILDEV_SERVICE, SFTP_SERVICE
from oops.services.docker import parse_image_tag
from oops.services.git import get_submodule_sha
from oops.utils.helpers import filter_and_clean
from oops.utils.net import parse_repository_url
from oops.utils.render import print_warning
from oops_engine.addons import find_addons, find_modified_addons
from oops_engine.compat import List, NamedTuple, Optional, Tuple, Union

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


def parse_text_file(content: str, unique: bool = True) -> list:
    """Parse a text file's content into a list of non-empty, stripped lines.

    Args:
        content: Raw file content as a string.
        unique (bool): Whether to deduplicate the result. Defaults to True.

    Returns:
        List of cleaned, non-empty lines.
    """

    return filter_and_clean(content.splitlines(), unique)


def read_and_parse(path: Path, unique: bool = True) -> list[str]:
    """Read a text file and return its non-empty, sorted lines.

    Args:
        path: Path to the text file to read.
        unique (bool): Whether to deduplicate the result. Defaults to True.

    Returns:
        Sorted list of cleaned, non-empty lines from the file.
    """
    return sorted(parse_text_file(path.read_text(), unique))


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
    try:
        res = read_and_parse(path / config.project.file_odoo_version)
    except FileNotFoundError as error:
        raise ValueError() from error
    if not res:
        raise ValueError()
    return parse_image_tag(res[0])


def read_tagged_block(filepath: Union[str, Path], start_tag: str, end_tag: str) -> str:
    """Return the raw content between start_tag and end_tag in a file.

    Args:
        filepath: Path to the file to read.
        start_tag: Exact string marking the beginning of the block.
        end_tag: Exact string marking the end of the block.

    Returns:
        The text between the two tags, or an empty string when the file does
        not exist or the tags are not found.
    """
    path = Path(filepath)
    if not path.exists():
        return ""
    m = re.search(re.escape(start_tag) + r"(.*?)" + re.escape(end_tag), path.read_text(), re.DOTALL)
    return m.group(1) if m else ""


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
        log.info(f"File {filepath} does not exist, creating it...")

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
        log.info(f"Updating {filepath}...")
        if dry_run:
            # click.echo("[dry-run]: \n" + new_file_content)
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

    log.info(f"No changes detected in {filepath}, skipping update.")
    return False


# ---------------------------------------------------------------------------
# Symlinks
# ---------------------------------------------------------------------------


def create_symlink(
    addon_dir: Path,
    repo_path: Path,
    quiet: bool = False,
) -> Optional[str]:
    """Create a symlink at the repo root pointing to an addon directory.

    Skips creation if a file or symlink with the same name already exists at
    the repo root, printing a warning in that case.

    Args:
        addon_dir: Path to the addon directory to link.
        repo_path: Repository root where the symlink will be created.
        quiet: If True, suppress the skip message when a collision is found.

    Returns:
        The symlink name (stem of addon_dir) if created, or None if skipped.
    """
    link_name = addon_dir.name
    link_path = repo_path / link_name
    target_rel = relpath(repo_path, addon_dir)
    if link_path.exists() or link_path.is_symlink():
        if not quiet:
            click.echo(f"  [skip] {link_name} already exists")
        return None
    os.symlink(target_rel, link_path)

    return link_name


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


def get_symlink_map(path: Path) -> dict:
    """Build a mapping of symlink parent directories to their single target name.

    Args:
        path: Root directory to scan for symlinks.

    Returns:
        Dict mapping each parent directory path to one target name.
        Assumes at most one symlink per parent directory.
    """

    # FIXME: assume there is only one symlink per submodule for now
    return {str(Path(t).parent): Path(t).name for t in list_symlinks(path)}


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


def rewrite_symlinks(repo, moved: list[Tuple[str, str]]) -> int:
    """Rewrite every symlink that referenced a moved path. Returns count."""
    rewrites = 0

    for root, dirs, files in os.walk(repo.working_dir):
        if ".git" in dirs:
            dirs.remove(".git")
        for fname in dirs + files:
            p = Path(root) / fname
            if not p.is_symlink():
                continue
            for oldp, newp in moved:
                if rewrite_symlink(p, oldp, newp):
                    rewrites += 1
                    repo.index.add([str(p)])
                    break
    return rewrites


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

    log.debug(f"[oops] materialize: {symlink_path} -> {target}")
    log.debug(f"[oops] tmp copy:   {tmp}")

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


def get_excluded_addon_names(repo_path: Path) -> list:
    """Return addon names that should be excluded from pre-commit checks.

    An addon is excluded when it is not installable or its author does not
    match ``config.manifest.author`` (i.e. it is a third-party addon).

    Args:
        repo_path: Root directory of the local repository.

    Returns:
        Sorted list of technical addon names to exclude.
    """
    res = []
    for addon in find_addons(repo_path, shallow=True):
        if not addon.installable or config.manifest.author.lower() not in addon.author.lower():
            res.append(addon.technical_name)
    return sorted(res)


def get_filtered_addon_names(repo_path: Path) -> list:
    """Return names of owned, installable, non-symlinked addons.

    Selects addons that are directly in the repository (not symlinks to
    third-party modules), are installable, and are authored by
    ``config.manifest.author``. Intended as the default scope for manifest
    lint and fix commands.

    Args:
        repo_path: Root directory of the local repository.

    Returns:
        Sorted list of technical addon names matching the criteria.
    """
    res = []
    for addon in find_addons(repo_path, shallow=True):
        if not addon.symlink and addon.installable and config.manifest.author.lower() in addon.author.lower():
            res.append(addon.technical_name)
    return sorted(res)


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

    # TODO: check content
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


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------


def build_compose(
    odoo_version: float,
    image: str,
    port: int,
    prefix: str,
    dev: bool,
    with_maildev: bool,
    with_sftp: bool,
) -> str:
    """Render a docker-compose.yml file from the project template.

    Args:
        odoo_version: Numeric Odoo major version (e.g. ``17.0``). Used to select
            the appropriate Postgres image (``pgvector`` for 19+, plain ``postgres``
            for earlier versions).
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
        postgres_image="pgvector/pgvector:pg16" if odoo_version >= 19 else "postgres:16.0",
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


# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------


def decode_payload(pos: int) -> str:
    """¯\\_(ツ)_/¯"""
    ...

    _PAYLOAD = [
        "eNpzSczNU0gpTUnVUajML1UvS1XITS0uTk1RKC1QKMlIVSguTcrNTynNSS1WSExPzMzT09MDANZmEgI=",
        (
            "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"
            "ZKz2XQ=="
        ),
    ]

    import base64
    import zlib

    try:
        content = zlib.decompress(base64.b64decode(_PAYLOAD[pos])).decode("utf-8")
        return content
    except Exception:
        return ""


class OdooSourcesDirs(NamedTuple):
    community: Path
    enterprise: Path
    themes: Path


def get_odoo_sources_dirs(version: str, base_dir: Optional[Path] = None) -> OdooSourcesDirs:
    """Resolve community, enterprise, and themes source directories for an Odoo version.

    The base directory is taken from ``base_dir`` when provided, otherwise falls back
    to ``odoo.sources_dir`` in ``~/.oops.yaml``. The version sub-directory is created
    if it does not exist yet.

    Args:
        version: Odoo version string used as the sub-directory name (e.g. ``"17.0"``).
        base_dir: Optional explicit root for Odoo sources. Overrides the config value.

    Returns:
        An ``OdooSourcesDirs`` named tuple with ``community``, ``enterprise``, and
        ``themes`` ``Path`` fields pointing to ``<base_dir>/<version>/{community,
        enterprise,themes}``. Paths are returned regardless of whether they exist
        on disk — the caller is responsible for checking existence.

    Raises:
        click.UsageError: When neither ``base_dir`` nor ``odoo.sources_dir`` is set.
    """
    resolved = base_dir or config.odoo.sources_dir
    if resolved is None:
        raise ConfigError("No base directory provided. Set odoo.sources_dir in ~/.oops.yaml.")
    target = resolved / version
    target.mkdir(parents=True, exist_ok=True)
    return OdooSourcesDirs(
        community=target / "community",
        enterprise=target / "enterprise",
        themes=target / "themes",
    )


class OdooSourcesStatus(NamedTuple):
    """Availability of community, enterprise, and themes sources for one Odoo version."""

    version: str
    community: bool
    enterprise: bool
    themes: bool
    path: Path

    @property
    def available(self) -> int:
        """Number of sources present on disk (0–3)."""
        return sum((self.community, self.enterprise, self.themes))

    @property
    def complete(self) -> bool:
        """True when all three sources are present."""
        return self.available == 3


def list_odoo_sources_versions(base_dir: Optional[Path] = None) -> "List[OdooSourcesStatus]":
    """List available Odoo source versions with per-source completion status.

    Scans ``sources_dir`` for version sub-directories and checks which of
    community, enterprise, and themes are present on disk.

    Args:
        base_dir: Optional explicit root for Odoo sources. Overrides config value.

    Returns:
        A list of :class:`OdooSourcesStatus` sorted by version name, each showing
        which sources exist.  Returns an empty list when the directory does not
        exist yet.

    Raises:
        click.UsageError: When neither ``base_dir`` nor ``odoo.sources_dir`` is set.
    """
    resolved = base_dir or config.odoo.sources_dir
    if resolved is None:
        raise ConfigError("No base directory provided. Set odoo.sources_dir in ~/.oops.yaml.")
    if not resolved.exists():
        return []
    return [
        OdooSourcesStatus(
            version=d.name,
            community=(d / "community").exists(),
            enterprise=(d / "enterprise").exists(),
            themes=(d / "themes").exists(),
            path=d,
        )
        for d in sorted(resolved.iterdir())
        if d.is_dir()
    ]


def require_odoo_sources(base_dir: Optional[Path] = None) -> "List[OdooSourcesStatus]":
    resolved = base_dir or config.odoo.sources_dir
    if resolved is None:
        raise ConfigError("No base directory provided. Set odoo.sources_dir in ~/.oops.yaml.")

    if not resolved.exists():
        raise OopsError("No sources available, please use the download command first.")

    return [
        OdooSourcesStatus(
            version=d.name,
            community=(d / "community").exists(),
            enterprise=(d / "enterprise").exists(),
            themes=(d / "themes").exists(),
            path=d,
        )
        for d in sorted(resolved.iterdir())
        if d.is_dir()
    ]
