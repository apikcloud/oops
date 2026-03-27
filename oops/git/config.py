# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: config.py — oops/git/config.py

import subprocess
from dataclasses import dataclass
from pathlib import Path

from oops.utils.compat import Optional
from oops.utils.tools import run


@dataclass
class GitModule:
    """Class for handling individual git submodule configuration."""

    path: str
    branch: str
    url: str
    pr: bool
    name: str = ""


def git_config_submodule(filepath: str, submodule: str, key: str, value: str) -> None:
    """Set a submodule configuration value in a git config file.

    Args:
        filepath: Path to the config file (usually .gitmodules)
        submodule: Name of the submodule
        key: Configuration key
        value: Configuration value
    """
    cmd = [
        "git",
        "config",
        "-f",
        filepath,
        f"submodule.{submodule}.{key}",
        value,
    ]
    run(cmd, name="config")


def get_submodule_config(filepath: str, name: str, key: str) -> Optional[str]:
    """Get a submodule configuration value from a git config file.

    Args:
        filepath: Path to the config file (usually .gitmodules)
        name: Name of the submodule
        key: Configuration key

    Returns:
        Configuration value or None if not found
    """
    output = run(
        ["git", "config", "-f", filepath, f"submodule.{name}.{key}"],
        capture=True,
        check=False,
    )

    if output:
        return output.strip()

    return None


def git_get_regexp(gitmodules: Path, pattern: str) -> list:
    """Get all git config values matching a regexp pattern.

    Args:
        gitmodules: Path to .gitmodules file
        pattern: Regexp pattern to match keys

    Returns:
        List of (key, value) tuples
    """
    try:
        out = run(
            ["git", "config", "-f", str(gitmodules), "--get-regexp", pattern],
            capture=True,
        )

        if not out:
            return []

        kv = []
        for line in out.splitlines():
            k, v = line.split(" ", 1)
            kv.append((k.strip(), v.strip()))
        return kv
    except subprocess.CalledProcessError:
        return []
