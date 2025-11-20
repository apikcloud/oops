"""Git versioning operations - Tags, releases, and semantic versioning."""

import re
import subprocess

from oops.utils.compat import Optional
from oops.utils.tools import run

# Semantic versioning pattern: v1.2.3
SEMVER_PATTERN = re.compile(r"^v(?P<x>0|[1-9]\d*)\.(?P<y>0|[1-9]\d*)\.(?P<z>0|[1-9]\d*)$")


def get_last_tag() -> Optional[str]:
    """Get the last git tag.

    Returns:
        Last tag name or None if no tags exist or not a git repository
    """
    try:
        out = run(["git", "describe", "--tags", "--abbrev=0"], capture=True)
        return out.strip() if out else None
    except subprocess.CalledProcessError:
        return None


def get_last_release() -> Optional[str]:
    """Get the last git tag that looks like a semantic version (vX.Y.Z).

    Returns:
        Last release tag or None if no valid semver tag found
    """
    try:
        last_tag = get_last_tag()
        if not last_tag:
            return None
    except Exception:
        return None

    if not bool(SEMVER_PATTERN.match(last_tag)):
        return None

    return last_tag


def get_next_releases() -> tuple:
    """Calculate next (normal, fix, major) release tags based on last release.

    Returns:
        Tuple of (normal, fix, major) version strings
        - normal: bump minor version (v1.2.3 -> v1.3.0)
        - fix: bump patch version (v1.2.3 -> v1.2.4)
        - major: bump major version (v1.2.3 -> v2.0.0)

    Raises:
        ValueError: If no valid release found or format is invalid
    """
    last_release = get_last_release()

    if not last_release:
        raise ValueError("No valid release found")

    m = SEMVER_PATTERN.match(last_release)

    if not m:
        raise ValueError(f"Last release tag '{last_release}' is not in valid semver format")

    x, y, z = int(m.group("x")), int(m.group("y")), int(m.group("z"))

    normal = f"v{x}.{y + 1}.0"
    fix = f"v{x}.{y}.{z + 1}"
    major = f"v{x + 1}.0.0"

    return normal, fix, major


def is_valid_semver(tag: str) -> bool:
    """Check if a tag follows semantic versioning format (vX.Y.Z).

    Args:
        tag: Tag name to validate

    Returns:
        True if tag is valid semver, False otherwise
    """
    return bool(SEMVER_PATTERN.match(tag))
