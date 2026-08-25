# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: helpers.py — tests/helpers.py

"""Shared test helpers for the oops test suite."""

from oops.core.models import AddonInfo


def make_addon(
    technical_name: str = "test_addon",
    python_deps: list = None,
    version: str = "16.0.1.0.0",
    maintainers: list = None,
    summary: str = "",
    external_dependencies: dict = None,
) -> AddonInfo:
    """Build a minimal AddonInfo for tests.

    - Pass ``python_deps`` to populate ``external_dependencies["python"]``.
    - Pass ``external_dependencies`` directly when you need non-python keys or an empty dict.
    """
    if external_dependencies is None:
        external_dependencies = {"python": python_deps or []}
    return AddonInfo(
        path=f"/fake/{technical_name}",
        rel_path="",
        technical_name=technical_name,
        symlink=False,
        root=True,
        version=version,
        author="Apik",
        maintainers=maintainers or [],
        depends=[],
        summary=summary,
        external_dependencies=external_dependencies,
        installable=True,
    )


def patch_requirements_addons(monkeypatch, addons: list) -> None:
    """Replace find_addons() in the requirements module so tests control which addons are scanned."""
    monkeypatch.setattr("oops.io.requirements.find_addons", lambda *a, **kw: iter(addons))
