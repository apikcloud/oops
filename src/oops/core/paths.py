# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: paths.py — oops/core/paths.py

import os
from pathlib import Path

WORKING_DIR = Path.cwd()

# ---------------------------------------------------------------------------
# Config file
# ---------------------------------------------------------------------------

CONFIG_FILENAME = ".oops.yaml"
CONFIG_GLOBAL = Path.home() / CONFIG_FILENAME  # ~/.oops.yaml
CONFIG_LOCAL = Path(CONFIG_FILENAME)  # ./.oops.yaml  (resolved at runtime vs cwd)
CONFIG_PATHS = [
    CONFIG_GLOBAL,
    CONFIG_LOCAL,
]  # order of precedence for config file discovery

# ---------------------------------------------------------------------------
# Odoo project conventions (DEPRECATED)
# ---------------------------------------------------------------------------

# TODO: PR_dir must be replace by `config.pull_request_dir`
PR_DIR = "PRs"  # pull-request addon symlink directory
UNPORTED_DIR = "__unported__"  # unported addons directory inside an addon path

# ---------------------------------------------------------------------------
# Stats / usage-tracking data directory
# ---------------------------------------------------------------------------


def stats_dir() -> Path:
    """Return the oops data directory, respecting ``XDG_DATA_HOME``.

    Returns:
        ``$XDG_DATA_HOME/oops`` when the env var is set, otherwise
        ``~/.local/share/oops``.
    """
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "oops"


def stats_file() -> Path:
    """Return the path to the usage-event JSONL file.

    Returns:
        ``<stats_dir>/stats.jsonl``
    """
    return stats_dir() / "stats.jsonl"


def stats_flush_marker() -> Path:
    """Return the path to the flush-timestamp marker file.

    Returns:
        ``<stats_dir>/stats_last_flush``
    """
    return stats_dir() / "stats_last_flush"
