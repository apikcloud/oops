# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: helpers.py — tests/helpers.py

"""Shared test factories."""

from typing import List, Optional

from oops_engine.models import Addon


def make_addon(
    technical_name: str = "addon",
    version: str = "17.0.1.0.0",
    author: str = "Apik",
    maintainers: Optional[List[str]] = None,
    summary: str = "Test addon",
    depends: Optional[List[str]] = None,
    external_dependencies: Optional[dict] = None,
    installable: bool = True,
    website: Optional[str] = None,
) -> Addon:
    """Build a minimal `Addon` for tests, with sane defaults for unused fields."""
    return Addon(
        path=f"/tmp/{technical_name}",
        rel_path="",
        technical_name=technical_name,
        symlink=False,
        root=True,
        version=version,
        author=author,
        maintainers=maintainers if maintainers is not None else [],
        depends=depends if depends is not None else [],
        summary=summary,
        external_dependencies=external_dependencies if external_dependencies is not None else {},
        installable=installable,
        website=website,
    )
