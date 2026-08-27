# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: loc.py — oops_engine/loc.py

"""Per-addon line-of-code statistics via the external `cloc` binary.

cloc is treated as an optional dependency: when absent, every call returns
a zeroed LocStats and a single warning is logged on the first lookup.

Only the `code` field is exposed; `blank` and `comment` are intentionally
dropped. Markdown and reStructuredText are merged into `docs`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from oops_engine.fingerprint import fingerprint_directory
from oops_engine.identity import local_repo_id
from oops_engine.logger import log
from oops_engine.models import LocStats
from oops_engine.paths import project_kb_path
from oops_engine.store import get_cached_loc, write_cached_loc
from oops_engine.utils import run

CLOC_LANGS = "Python,XML,JavaScript,Markdown,reStructuredText"


@lru_cache(maxsize=1)
def _has_cloc() -> bool:
    if shutil.which("cloc") is not None:
        return True
    log.warning(
        "'cloc' not found in PATH — LOC counts unavailable. "
        "Install it globally (e.g. `apt install cloc`) to enable LOC reporting."
    )
    return False


@lru_cache(maxsize=None)
def get_addon_loc(path: str) -> LocStats:
    """Return code-line counts for the given absolute addon directory.

    Soft-fails (returns a zeroed LocStats) if cloc is missing, the directory
    is empty of relevant languages, or cloc output is unparseable.
    """
    if not _has_cloc():
        return LocStats()

    try:
        raw = run(
            ["cloc", "--json", "--quiet", f"--include-lang={CLOC_LANGS}", path],
            check=True,
            capture=True,
            name="cloc",
        )
    except subprocess.CalledProcessError as exc:
        log.debug("cloc failed on %s (exit %s)", path, exc.returncode)
        return LocStats()

    if not raw:
        return LocStats()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.debug("cloc emitted non-JSON output for %s", path)
        return LocStats()

    md = data.get("Markdown", {})
    rst = data.get("reStructuredText", {})
    return LocStats(
        python=int(data.get("Python", {}).get("code", 0)),
        xml=int(data.get("XML", {}).get("code", 0)),
        javascript=int(data.get("JavaScript", {}).get("code", 0)),
        docs=int(md.get("code", 0)) + int(rst.get("code", 0)),
    )


def get_addon_loc_cached(repo_path: Path, addon_path: str) -> LocStats:
    """Cached wrapper around `get_addon_loc()`, keyed by content fingerprint.

    `get_addon_loc()`'s own `@lru_cache` is in-process only — gone the moment
    the CLI exits. This persists the result in the project KB's SQLite file,
    keyed by a content fingerprint of the addon directory (see
    `oops_engine.fingerprint`) so unchanged addons skip the `cloc` subprocess
    on the next invocation. Works even when no project KB has been built yet
    — the cache file/schema is created on first use.
    """
    fingerprint = fingerprint_directory(Path(addon_path))
    repo_id = local_repo_id(repo_path)
    db_path = project_kb_path(repo_path)

    cached = get_cached_loc(db_path, repo_id, addon_path, fingerprint)
    if cached is not None:
        return LocStats(**cached)

    loc = get_addon_loc(addon_path)
    write_cached_loc(db_path, repo_id, addon_path, fingerprint, asdict(loc))
    return loc
