# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: versioning.py — oops/utils/versioning.py


import re
import subprocess

from oops.io.tools import run
from oops.utils.compat import Optional

# Semantic versioning pattern: v1.2.3
SEMVER_PATTERN = re.compile(r"^v(?P<x>0|[1-9]\d*)\.(?P<y>0|[1-9]\d*)\.(?P<z>0|[1-9]\d*)$")


def get_last_tag() -> Optional[str]:
    """Return the most recent git tag in the current repository.

    Returns:
        Most recent tag name, or None if no tags exist or the command fails.
    """
    try:
        out = run(["git", "describe", "--tags", "--abbrev=0"], capture=True)
        return out.strip() if out else None
    except subprocess.CalledProcessError:
        return None


def get_last_release() -> Optional[str]:
    """Return the most recent git tag that matches semver format (vX.Y.Z).

    Returns:
        Last semver-formatted release tag, or None if none is found.
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
    """Compute the next minor, patch, and major release tags from the last release.

    Returns:
        Tuple of (minor_bump, patch_bump, major_bump) version strings, e.g.
        ``("v1.3.0", "v1.2.4", "v2.0.0")`` when the last release is ``v1.2.3``.

    Raises:
        ValueError: If no valid semver release tag is found.
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
    """Check whether a tag string follows the vX.Y.Z semver format.

    Args:
        tag: Tag name to validate.

    Returns:
        True if the tag matches the semver pattern, False otherwise.
    """
    return bool(SEMVER_PATTERN.match(tag))
