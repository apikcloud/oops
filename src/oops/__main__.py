# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: __main__.py — oops/__main__.py

"""Allow `python -m oops` to invoke the CLI (used by the dashboard subprocess bridge)."""

from oops.cli import main

if __name__ == "__main__":
    main()
