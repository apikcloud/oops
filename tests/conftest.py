"""Shared pytest fixtures for the oops test suite."""

import pytest

MINIMAL_CONFIG = (
    "version: 1\n"
    "images:\n"
    "  source:\n    repository: test/repo\n    file: tags.json\n"
    "  collections:\n    - production\n"
    "  registries:\n"
    "    deprecated:\n      - loginline\n"
    "    warn:\n      - odoo\n"
    "manifest:\n  author: Acme\n"
)


@pytest.fixture(autouse=True)
def _patch_config(tmp_path, monkeypatch):
    """Provide a minimal valid config for every test.

    Patches _CONFIG_PATHS so that load_config() finds a real file and resets
    the _LazyConfig singleton so each test starts from a clean state.
    """
    from oops.core import config as config_module

    cfg_file = tmp_path / ".oops.yaml"
    cfg_file.write_text(MINIMAL_CONFIG)

    monkeypatch.setattr("oops.core.config._CONFIG_PATHS", [cfg_file])
    # Reset the lazy singleton so the next access triggers a fresh load.
    monkeypatch.setattr(config_module._LazyConfig, "_cfg", None)
