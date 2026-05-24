# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — src/oops/commands/depends/check.py

"""
Checks the dependencies of one or more modules by comparing the existing references (XML)
and inheritances (models, wizards, controllers) with the list of dependencies contained in the manifests.
"""

from oops.commands.base import command
from oops.services.git import require_repository


@command(name="check", help=__doc__)
def main():

    _, repo_path = require_repository()
    raise NotImplementedError()
