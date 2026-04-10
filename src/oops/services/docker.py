# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: docker.py — oops/services/docker.py

import re
import warnings
from datetime import date

from oops.core.config import config
from oops.core.exceptions import DeprecatedRegistryWarning, UnusualRegistryWarning
from oops.core.models import ImageInfo
from oops.utils.compat import Optional
from oops.utils.helpers import date_from_string
from oops.utils.net import make_json_get
from oops.utils.render import render_table

# try:
#     import odoo as odoo
# except ImportError:
#     odoo = None  # type: ignore
#     warnings.warn(
#         "Odoo is not available, some features will not be available.", ImportWarning, stacklevel=0
#     )


def warn_deprecated_registry(name: str) -> None:
    """Issue a DeprecatedRegistryWarning for a known deprecated Docker registry.

    Args:
        name: Name of the deprecated registry.
    """
    warnings.warn(
        f"You should use one of these registries ({', '.join(config.images.registries.recommended)}) as a replacement for '{name}'.",  # noqa: E501
        DeprecatedRegistryWarning,
        stacklevel=3,
    )


def warn_unusual_registry(name: str) -> None:
    """Issue an UnusualRegistryWarning for an unrecognised Docker registry.

    Args:
        name: Name of the unusual registry.
    """
    warnings.warn(
        f"You should use one of these registries ({', '.join(config.images.registries.recommended)}) as a replacement for '{name}'.",  # noqa: E501
        UnusualRegistryWarning,
        stacklevel=3,
    )


def parse_image_tag(tag: str) -> ImageInfo:
    """Parse an Odoo Docker image tag into its structured components.

    Expected pattern: ``<registry>/<repository>:<major>[.0][-<YYYYMMDD>][-enterprise][-legacy]``

    Examples: ``odoo:19``, ``apik/odoo:19.0-20250919-enterprise``

    Args:
        tag: Full Docker image tag string to parse.

    Returns:
        ImageInfo populated with registry, repository, version, release date, and flags.

    Raises:
        ValueError: If the tag is missing a colon separator or has an unrecognised version format.
    """
    # Defaults
    registry = "odoo"
    repository = "odoo"
    major_version: float
    release: Optional[date] = None
    enterprise = False
    legacy = False

    # Split registry/repository and tag
    if ":" not in tag:
        raise ValueError(f"Invalid image tag: {tag}")
    left, tag_part = tag.split(":", 1)

    # Handle registry/repository
    if "/" in left:
        registry, repository = left.split("/", 1)
    else:
        registry = left
        repository = "odoo"

    # Extract flags
    if "enterprise" in tag_part:
        enterprise = True
        tag_part = tag_part.replace("-enterprise", "")
    if "legacy" in tag_part:
        legacy = True
        tag_part = tag_part.replace("-legacy", "")

    # Match version and optional release date
    m = re.match(r"^(?P<version>\d+(?:\.\d+)?)(?:-(?P<release>\d{8}))?$", tag_part)
    if not m:
        raise ValueError(f"Unrecognized tag format: {tag_part}")

    version_str = m.group("version")
    release_str = m.group("release")

    major_version = float(version_str)

    if release_str:
        release = date_from_string(release_str)

    return ImageInfo(
        image=tag,
        registry=registry,
        repository=repository,
        major_version=major_version,
        release=release,
        enterprise=enterprise,
        legacy=legacy,
    )


def fetch_odoo_images(collections: Optional[list] = None) -> list:
    """Fetch available Odoo Docker images filtered by collection.

    Args:
        collections: List of collection names to include. Defaults to config.images.collections.

    Returns:
        List of ImageInfo objects matching the requested collections.
    """
    # {
    #     "id": 976836335,
    #     "last_updated": "2025-09-21T13:03:37.077452Z",
    #     "name": "19.0-20250921-enterprise",
    #     "org": "apik",
    #     "repo": "odoo",
    #     "image": "apik/odoo:19.0-20250921-enterprise",
    #     "full_size": 779130948,
    #     "digest": "sha256:ca68c876ab9d614e27df74ec4e954d9a466c576a6a6c7c24d6ae8cde0a610683",
    #     "state": null,
    #     "collection": "production",
    #     "version": 19,
    #     "edition": "enterprise",
    #     "release": "20250921"
    # },

    if collections is None:
        collections = config.images.collections
    data = make_json_get(config.images.source.url)

    items = [ImageInfo.from_raw_dict(vals) for vals in data]

    def filter_out(item):
        if item.collection in collections:
            return item

    return list(filter(filter_out, items))


def check_image(image: ImageInfo, strict: bool = True) -> list:
    """Check an Odoo Docker image for registry and age issues.

    In strict mode, issues are raised as warnings. Otherwise they are collected
    and returned as strings for the caller to handle.

    Args:
        image: ImageInfo to validate.
        strict: If True, emit Python warnings directly. Defaults to True.

    Returns:
        List of warning message strings (empty when strict is True or no issues found).
    """
    warnings = []
    recommmended = ", ".join(config.images.registries.recommended)
    if image.registry not in config.images.registries.recommended:
        if image.registry in config.images.registries.deprecated:
            if strict:
                warn_deprecated_registry(image.registry)
            else:
                warnings.append(
                    f"You should use one of these registries ({recommmended}) as a replacement for '{image.registry}'."
                )

        if image.registry in config.images.registries.warn:
            if strict:
                warn_unusual_registry(image.registry)
            else:
                warnings.append(
                    f"You should use one of these registries ({recommmended}) as a replacement for '{image.registry}'."
                )

    if image.age and image.age > config.images.release_warn_age_days:
        warnings.append(
            f"The current Odoo image is {image.age} days old, consider updating it",
        )

    return warnings


def find_available_images(release: date, enterprise: bool, version: float) -> list:
    """Find Odoo images newer than a given release date that match version and edition.

    Args:
        release: Reference release date; only images with a newer release are returned.
        enterprise: If True, filter for enterprise images; otherwise community.
        version: Odoo major version to filter on (e.g. 18.0).

    Returns:
        List of matching ImageInfo objects sorted by release date descending,
        each annotated with a delta attribute (days from release).
    """
    available = fetch_odoo_images()

    # TODO: improve filtering, add conditions on release date
    def filter_out(item):
        if (
            item.major_version == version
            and item.enterprise == enterprise
            and item.release > release
            and item.collection in config.images.collections
        ):
            return item

    items = list(filter(filter_out, available))

    if not items:
        return []

    items = sorted(items, key=lambda item: item.release, reverse=True)

    def improve(item):
        item.delta = abs((release - item.release).days)
        return item

    return list(map(improve, items))


def format_available_images(images: list, include_index: bool = False) -> str:
    """Render a list of available Odoo images as a formatted table string.

    Args:
        images: List of ImageInfo objects to display (as returned by find_available_images).
        include_index: If True, prepend a numeric index column. Defaults to False.

    Returns:
        Formatted table string, or an empty string if images is empty.
    """
    if not images:
        return ""

    rows = []

    headers = ["Release", "Delta (days)", "Source"]
    if include_index:
        headers.insert(0, "Index")

    for item in images:
        rows.append([item.release.isoformat(), item.delta, item.source])

    return render_table(rows, headers=headers, index=include_index)
