# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: logger.py — src/oops_engine/logger.py


import logging

# setup
log = logging.getLogger("oops")
log.setLevel(logging.INFO)
log.propagate = False
