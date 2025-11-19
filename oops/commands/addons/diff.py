#!/usr/bin/env python3

import logging
import subprocess
from pathlib import Path

import click

from oops.git.gitutils import git_top

logging.basicConfig(level=logging.INFO)


def run(cmd):
    return subprocess.check_output(cmd, text=True).strip()


def get_changed_files(mode: str):
    """
    mode = "branch" → compare HEAD to origin/main
    mode = "tag"    → compare HEAD to the latest tag
    """
    if mode == "branch":
        base = "origin/main"
        diff_range = f"{base}...HEAD"
    elif mode == "tag":
        last_tag = run(["git", "describe", "--tags", "--abbrev=0"])
        diff_range = f"{last_tag}..HEAD"
    else:
        raise ValueError("mode must be 'branch' or 'tag'")

    return run(["git", "diff", "--name-only", diff_range]).splitlines()


def find_modified_addons(files: list) -> list:
    addons = set()
    for f in files:
        p = Path(f)
        # Remonter l’arbo jusqu’à trouver un manifeste
        for parent in [p] + list(p.parents):
            if (parent / "__manifest__.py").exists() or (parent / "__openerp__.py").exists():
                addons.add(str(parent))
                break
    return sorted(addons)


@click.command(name="diff")
@click.argument("mode", type=click.Choice(["branch", "tag"], case_sensitive=False))
def main(
    mode: str,
):
    local_repo = git_top()
    changed = get_changed_files(mode=mode)
    addons = find_modified_addons(changed)
    print("Changed addons:", addons)
