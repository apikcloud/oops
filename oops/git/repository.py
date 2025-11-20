"""Git repository operations and helpers."""

import contextlib
import subprocess
from pathlib import Path

from oops.core.models import CommitInfo
from oops.utils.compat import Optional, Union
from oops.utils.io import find_addons_extended
from oops.utils.render import human_readable
from oops.utils.tools import run


def get_last_commit(path: Optional[str] = None) -> Optional[CommitInfo]:
    """Get information about the last commit.

    Args:
        path: Optional path to git repository (uses current directory if None)

    Returns:
        CommitInfo object or None if not a git repo or no commits
    """
    cmd = ["git", "log", "-1", "--date=iso-strict", "--pretty=format:%h;%an;%ae;%ad;%s"]

    if path:
        cmd.insert(1, "-C")
        cmd.insert(2, path)

    try:
        output = run(cmd, capture=True)

        if not output:
            return None

        return CommitInfo.from_string(output)

    except subprocess.CalledProcessError:
        return None


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


def list_available_addons(root: Path):
    """List all available addons from git submodules.

    Yields addon information from each submodule. Updates submodules if needed.

    Args:
        root: Root path of the git repository

    Yields:
        AddonInfo objects for each addon found

    Raises:
        FileNotFoundError: If .gitmodules doesn't exist
    """
    # Import here to avoid circular dependency
    from oops.git.config import parse_submodules_extended  # noqa: PLC0415
    from oops.git.submodules import submodule_update  # noqa: PLC0415

    gitmodules = root / ".gitmodules"

    if not gitmodules.exists():
        raise FileNotFoundError()

    subs = parse_submodules_extended(gitmodules)

    for _, info in subs.items():
        sub_path = info.get("path")
        if not sub_path:
            continue

        abs_path = root / sub_path

        if not abs_path.exists():
            with contextlib.suppress(subprocess.CalledProcessError):
                submodule_update(sub_path)

            # re-check
            if not abs_path.exists():
                continue

        yield from find_addons_extended(abs_path)
