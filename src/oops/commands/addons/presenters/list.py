# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: list.py — src/oops/commands/addons/presenters/list.py

from __future__ import annotations

from collections import Counter

from oops.core.models import Stat, StatGroup
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, SectionBlock, SummaryLayout, TableBlock, statgroup_to_panel
from oops.utils.render import colorize, human_readable, render_boolean
from oops_engine.compat import List, Optional, Tuple
from oops_engine.models import Addon, LocStats, Result

LOCATIONS = ("active", "local", "inactive")
CLASSIFICATIONS = ("custom", "oca", "third-party")
LOC_KEYS = ("python", "xml", "javascript", "docs", "total")


def _loc_dict(loc: Optional[LocStats]) -> dict:
    loc = loc or LocStats()
    return {
        "python": loc.python,
        "xml": loc.xml,
        "javascript": loc.javascript,
        "docs": loc.docs,
        "total": loc.total,
    }


def _summarize(addons: List[Addon]) -> dict:
    """Aggregate counters shared by the human panels and the machine ``summary``."""
    locations = Counter(addon.location for addon in addons)
    classifications = Counter(addon.classification for addon in addons)
    locs = [_loc_dict(addon.loc) for addon in addons]

    return {
        "total": len(addons),
        "by_location": {key: locations[key] for key in LOCATIONS},
        "by_classification": {key: classifications[key] for key in CLASSIFICATIONS},
        "loc": {key: sum(loc[key] for loc in locs) for key in LOC_KEYS},
    }


def _stat_groups(summary: dict) -> Tuple[StatGroup, StatGroup, StatGroup]:
    locations = summary["by_location"]
    classifications = summary["by_classification"]
    loc = summary["loc"]

    overview = StatGroup(
        name="summary",
        label="Summary",
        values=[
            Stat(name="local", label="Local", value=locations["local"]),
            Stat(name="active", label="Active", value=locations["active"]),
            Stat(name="inactive", label="Inactive", value=locations["inactive"]),
            Stat(name="total", label="Total", value=summary["total"]),
        ],
    )

    classification = StatGroup(
        name="classification",
        label="Classification",
        values=[
            Stat(name="custom", label="Custom", value=classifications["custom"]),
            Stat(name="oca", label="OCA", value=classifications["oca"]),
            Stat(name="third-party", label="Third-party", value=classifications["third-party"]),
        ],
    )

    lines = StatGroup(
        name="lines of code",
        label="Lines of code",
        values=[
            Stat(name="python", label="Python", value=loc["python"]),
            Stat(name="xml", label="XML", value=loc["xml"]),
            Stat(name="javascript", label="JavaScript", value=loc["javascript"]),
            Stat(name="docs", label="Docs", value=loc["docs"]),
            Stat(name="total", label="Total", value=loc["total"]),
        ],
    )

    return overview, classification, lines


def _addon_data(addon: Addon) -> dict:
    return {
        "technical_name": addon.technical_name,
        "path": f"{addon.rel_path}/{addon.technical_name}" if addon.rel_path else addon.technical_name,
        "location": addon.location,
        "classification": addon.classification,
        "version": addon.version,
        "installable": addon.installable,
        "summary": addon.summary,
        "author": addon.author,
        "maintainers": addon.maintainers,
        "website": addon.website,
        "depends": addon.depends,
        "external_dependencies": addon.external_dependencies,
        "submodule": addon.submodule or None,
        "branch": addon.branch or None,
        "pull_request": addon.pull_request,
        "loc": {**_loc_dict(addon.loc), "pct": addon.loc_pct},
    }


class ListPresenter(SimplePresenter[List[Addon]]):
    def to_human(self, result: Result[List[Addon]]) -> SummaryLayout:

        addons = result.unwrap

        stats = _stat_groups(_summarize(addons))

        columns = [
            ("Addon", "brand.primary", "left"),
            ("Symlink", "green", "center"),
            ("Submodule", "dim", "left"),
            ("Branch", "dim", "center"),
            ("PR", "green", "center"),
            ("Version", "brand.primary", "left"),
            ("Classification", "dim", ""),
            ("Author", "dim", ""),
            ("Py", "dim", "right"),
            ("XML", "dim", "right"),
            ("JS", "dim", "right"),
            ("Docs", "dim", "right"),
            ("LOC", "brand.primary", "right"),
        ]

        table = TableBlock(
            title="",
            columns=columns,
            rows=[
                [
                    addon.technical_name,
                    colorize(render_boolean(addon.symlink), "green"),
                    human_readable(addon.submodule),
                    human_readable(addon.branch),
                    colorize(render_boolean(bool(addon.pull_request)), "green"),
                    addon.version,
                    human_readable(addon.classification),
                    human_readable(addon.author),
                    str(addon.loc.python) if addon.loc else "",
                    str(addon.loc.xml) if addon.loc else "",
                    str(addon.loc.javascript) if addon.loc else "",
                    str(addon.loc.docs) if addon.loc else "",
                    str(addon.loc.total) if addon.loc else "",
                ]
                for addon in addons
            ],
        )

        section = SectionBlock(title="", panels=[statgroup_to_panel(s) for s in stats], tables=[table])

        return SummaryLayout(
            title="Addons",
            sections=[section],
            conclusion=ConclusionBlock(True, "All done"),
        )

    def to_data(self, result: Result[List[Addon]]) -> dict:
        addons = result.unwrap
        return {"summary": _summarize(addons), "addons": [_addon_data(addon) for addon in addons]}
