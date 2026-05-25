# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: changelog.py — src/oops/io/changelog.py

import re

from oops.core.compat import Dict, List, Optional
from oops.core.models import ChangelogSection


def _extract_section(changelog: str, version: str) -> str:

    version_bare = version.lstrip("v")
    version_pattern = rf"v?{re.escape(version_bare)}"

    sections = re.split(r"(?=^## )", changelog, flags=re.MULTILINE)
    for section in sections:
        if re.match(rf"## \[{version_pattern}\]", section):
            return section.strip()
    return ""


def parse_section(changelog: str, version: str) -> "Optional[ChangelogSection]":

    section = _extract_section(changelog, version)

    if not section:
        return None

    lines = section.splitlines()

    # Header : ## [2.9.1] - 2026-04-27
    header = re.match(r"## \[(.+?)\]\s*-?\s*(\d{4}-\d{2}-\d{2})", lines[0])
    version = header.group(1) if header else ""
    date_str = header.group(2) if header else ""

    entries: Dict[str, List[str]] = {}
    current = None

    for line in lines[1:]:
        if line.startswith("### "):
            current = line[4:].strip()
            entries[current] = []
        elif line.startswith("- ") and current:
            entries[current].append(line[2:].strip())
        elif line.startswith("  ") and current and entries[current]:
            entries[current][-1] += "\n" + line.strip()

    return ChangelogSection(version=version, date=date_str, entries=entries)
