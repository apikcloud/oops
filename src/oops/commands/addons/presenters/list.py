# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: list.py — src/oops/commands/addons/presenters/list.py

from __future__ import annotations

from collections import Counter
from dataclasses import asdict

from oops.core.compat import List, Tuple
from oops.core.models import AddonInfo, Result, Stat, StatGroup
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, SectionBlock, SummaryLayout, TableBlock, statgroup_to_panel
from oops.utils.render import colorize, human_readable, render_boolean


def _build_metrics(result: Result[List[AddonInfo]]) -> Tuple[StatGroup, StatGroup, StatGroup]:

    addons = result.unwrap

    total = len(addons)
    locations = Counter(addon.location for addon in addons)
    classifications = Counter(addon.classification for addon in addons)
    total_loc = sum(addon.loc.total for addon in addons if addon.loc)

    loc_sum_py = sum(addon.loc.python for addon in addons if addon.loc)
    loc_sum_xml = sum(addon.loc.xml for addon in addons if addon.loc)
    loc_sum_js = sum(addon.loc.javascript for addon in addons if addon.loc)
    loc_sum_docs = sum(addon.loc.docs for addon in addons if addon.loc)

    summary = StatGroup(
        name="summary",
        label="Summary",
        values=[
            Stat(name="local", label="Local", value=locations["local"]),
            Stat(name="active", label="Active", value=locations["active"]),
            Stat(name="inactive", label="Inactive", value=locations["inactive"]),
            Stat(name="total", label="Total", value=total),
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

    loc = StatGroup(
        name="lines of code",
        label="Lines of code",
        values=[
            Stat(name="python", label="Python", value=loc_sum_py),
            Stat(name="xml", label="XML", value=loc_sum_xml),
            Stat(name="javascript", label="JavaScript", value=loc_sum_js),
            Stat(name="docs", label="Docs", value=loc_sum_docs),
            Stat(name="total", label="Total", value=total_loc),
        ],
    )

    return summary, classification, loc


class ListPresenter(SimplePresenter[List[AddonInfo]]):
    def to_human(self, result: Result[List[AddonInfo]]) -> SummaryLayout:

        addons = result.unwrap

        stats = _build_metrics(result)

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

    def to_machine(self, result: "Result[List[AddonInfo]]") -> dict:

        metrics = _build_metrics(result)

        return {
            "data": [asdict(addon) for addon in result.unwrap],
            "metrics": [s.to_dict(summary=True) for s in metrics],
            "warnings": result.warnings,
        }
