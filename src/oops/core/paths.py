# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: paths.py — oops/core/paths.py

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
# Odoo project conventions
# ---------------------------------------------------------------------------

PR_DIR = "PRs"  # pull-request addon symlink directory
UNPORTED_DIR = "__unported__"  # unported addons directory inside an addon path
