# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: readme.py — src/oops_engine/readme.py


from pathlib import Path

# Standard OCA fragment order for a readme/ directory (concatenated in this order).
_OCA_README_FRAGMENTS = (
    "DESCRIPTION.rst",
    "CONTEXT.rst",
    "INSTALL.rst",
    "CONFIGURE.rst",
    "USAGE.rst",
    "DEVELOP.rst",
    "ROADMAP.rst",
    "KNOWN_ISSUES.rst",
    "CREDITS.rst",
    "HISTORY.rst",
    "CONTRIBUTORS.rst",
)


def detect_readme(module_path: Path) -> dict:
    """Detect and capture a module's README.

    Detection order (spec §5, §8.7):
        1. ``README.rst`` / ``README.md`` at the module root.
        2. An OCA ``readme/`` fragment directory (fragments concatenated in the
           standard OCA order; ``format="rst"``).
        3. ``static/description/index.html``.

    Args:
        module_path: Path to the Odoo module directory.

    Returns:
        ``{present: bool, format: "rst"|"md"|"html"|None, path: str|None,
        content: str|None}``. Content is captured raw — never converted.
    """
    empty = {"present": False, "format": None, "path": None, "content": None}

    for filename, fmt in (("README.rst", "rst"), ("README.md", "md")):
        candidate = module_path / filename
        if candidate.is_file():
            return {
                "present": True,
                "format": fmt,
                "path": f"{module_path.name}/{filename}",
                "content": candidate.read_text(encoding="utf-8", errors="replace"),
            }

    readme_dir = module_path / "readme"
    if readme_dir.is_dir():
        fragments = [f for f in _OCA_README_FRAGMENTS if (readme_dir / f).is_file()]
        if fragments:
            content = "\n\n".join((readme_dir / f).read_text(encoding="utf-8", errors="replace") for f in fragments)
            return {
                "present": True,
                "format": "rst",
                "path": f"{module_path.name}/readme/",
                "content": content,
            }

    index_html = module_path / "static" / "description" / "index.html"
    if index_html.is_file():
        return {
            "present": True,
            "format": "html",
            "path": f"{module_path.name}/static/description/index.html",
            "content": index_html.read_text(encoding="utf-8", errors="replace"),
        }

    return empty
