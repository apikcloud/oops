# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: versioning.py — oops/utils/versioning.py


import re
import subprocess
from collections import Counter

from oops.core.compat import Dict, List, Optional
from oops.core.models import Release, ReleaseType, Result
from oops.io.changelog import parse_section
from oops.io.tools import run

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


def _extract_file(tag, filename: str) -> Optional[str]:
    try:
        blob = tag.commit.tree[filename]
        content = blob.data_stream.read().decode("utf-8")
        return content
    except KeyError:
        return None


def read_releases(repo, changelog: bool = False) -> Result[List[Release]]:
    """Read all semver-tagged releases from a Git repository.

    Releases are returned newest-first. When ``changelog=True``, each release
    gets its :attr:`~oops.core.models.Release.changelog` field populated from
    the ``CHANGELOG.md`` file at the tagged commit.

    Args:
        repo: GitPython ``Repo`` instance.
        changelog: If True, parse the changelog section for each release.

    Returns:
        :class:`~oops.core.models.Result` wrapping a list of
        :class:`~oops.core.models.Release` objects.
    """
    result: Result[List[Release]] = Result()
    result.data = []

    releases = sorted(
        [t for t in repo.tags if SEMVER_PATTERN.match(t.name)],
        key=lambda t: t.commit.committed_datetime,
    )

    if not releases:
        return result

    for i, tag in enumerate(reversed(releases)):
        tag_date = tag.commit.committed_datetime.date()

        if i < len(releases) - 1:
            prev = releases[-(i + 2)]
            commit_count = len(list(repo.iter_commits(f"{prev.name}..{tag.name}")))
        else:
            commit_count = len(list(repo.iter_commits(tag.name)))

        author = tag.tag.tagger.name if tag.tag else tag.commit.author.name

        release = Release(
            name=tag.name,
            date=tag_date,
            author=author,
            commits=commit_count,
        )

        if changelog:
            content = _extract_file(tag, "CHANGELOG.md")
            if content:
                release.changelog = parse_section(content, tag.name)
            else:
                result.add_warning(f"No CHANGELOG found for release {tag.name}")

        result.data.append(release)
    return result


def count_release_types(releases: List[Release]) -> Dict:
    """Count releases grouped by :class:`~oops.core.models.ReleaseType`.

    Args:
        releases: List of releases to count.

    Returns:
        Dict mapping release type value (``"major"``, ``"minor"``, ``"fix"``,
        ``"unknown"``) to its count.
    """
    counter = Counter(item.release_type for item in releases)
    return {release_type.value: counter[release_type] for release_type in ReleaseType}
