# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: common.py — oops/commands/manifest/common.py

from pathlib import Path

import fixit
from fixit import Options, QualifiedRule

from oops.io.manifest import find_manifests
from oops.utils.compat import List, Optional

_RULES = [QualifiedRule("oops.rules.manifest")]


def collect_paths(repo_path: Path, names: Optional[List[str]] = None) -> List[Path]:
    """Return manifest paths under repo_path, optionally filtered by addon name.

    Args:
        repo_path: Repository root to scan.
        names: If provided, only include manifests whose addon name is in this list.

    Returns:
        List of resolved manifest file paths.
    """
    return [Path(p) for p in find_manifests(str(repo_path), names=names) if p]


def run_fixit(paths: List[Path], autofix: bool, show_diff: bool = False) -> int:
    """Run oops manifest rules over paths and return the number of violations.

    Args:
        paths: Manifest files to lint.
        autofix: If True, apply autofixes in place.
        show_diff: If True, print the autofix diff for each violation.

    Returns:
        Number of violations found.
    """
    options = Options(debug=False, config_file=None, rules=_RULES)
    violations = 0
    for result in fixit.fixit_paths(paths, autofix=autofix, options=options):
        if fixit.print_result(result, show_diff=show_diff):
            violations += 1
    return violations
