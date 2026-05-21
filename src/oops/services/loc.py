# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: loc.py — oops/services/loc.py

"""Per-addon line-of-code statistics via the external `cloc` binary.

cloc is treated as an optional dependency: when absent, every call returns
a zeroed LocStats and a single warning is printed on the first lookup.

Only the `code` field is exposed; `blank` and `comment` are intentionally
dropped. Markdown and reStructuredText are merged into `docs`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache

from oops.core.logger import log
from oops.io.tools import run
from oops.utils.render import print_warning

CLOC_LANGS = "Python,XML,JavaScript,Markdown,reStructuredText"


@dataclass(frozen=True)
class LocStats:
    python: int = 0
    xml: int = 0
    javascript: int = 0
    docs: int = 0  # Markdown + reStructuredText combined

    @property
    def total(self) -> int:
        return self.python + self.xml + self.javascript + self.docs


@lru_cache(maxsize=1)
def _has_cloc() -> bool:
    if shutil.which("cloc") is not None:
        return True
    print_warning(
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
