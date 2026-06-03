# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: list.py — src/oops/commands/addons/presenters/list.py

from __future__ import annotations

from collections import Counter

from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, SectionBlock, SummaryLayout, TableBlock
from oops.utils.render import colorize, human_readable, render_boolean


class ListPresenter(SimplePresenter[list]):
    def to_human(self, result: Result[list]) -> SummaryLayout:

        rows = result.unwrap

        total = len(rows)
        locations = Counter(row["location"] for row in rows)
        classifications = Counter(row["classification"] for row in rows)
        total_loc = sum(r["loc_total"] for r in rows)

        p1 = MetricsPanelBlock(
            "Summary",
            [
                ["Total", str(total)],
                ["Local", str(locations["local"])],
                ["Active", str(locations["active"])],
                ["Inactive", str(locations["inactive"])],
            ],
        )

        p2 = MetricsPanelBlock(
            "Classification",
            [
                ["Custom", str(classifications["custom"])],
                ["OCA", str(classifications["oca"])],
                ["Third-party", str(classifications["third-party"])],
            ],
        )

        loc_sum_py = sum(r["loc_python"] for r in rows)
        loc_sum_xml = sum(r["loc_xml"] for r in rows)
        loc_sum_js = sum(r["loc_js"] for r in rows)
        loc_sum_docs = sum(r["loc_docs"] for r in rows)

        p3 = MetricsPanelBlock(
            "Lines of code",
            [
                ["Python", str(loc_sum_py)],
                ["XML", str(loc_sum_xml)],
                ["JavaScript", str(loc_sum_js)],
                ["Docs", str(loc_sum_docs)],
                ["Total", str(total_loc)],
            ],
        )

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
                    row["addon"],
                    colorize(render_boolean(row["symlink"]), "green"),
                    human_readable(row["submodule"]),
                    human_readable(row["upstream"]),
                    colorize(render_boolean(row["pr"]), "green"),
                    row["version"],
                    human_readable(row["classification"]),
                    human_readable(row["author"]),
                    str(row["loc_python"]) if row["loc_python"] else "",
                    str(row["loc_xml"]) if row["loc_xml"] else "",
                    str(row["loc_js"]) if row["loc_js"] else "",
                    str(row["loc_docs"]) if row["loc_docs"] else "",
                    str(row["loc_total"]) if row["loc_total"] else "",
                ]
                for row in rows
            ],
        )

        section = SectionBlock(title="", panels=[p1, p2, p3], tables=[table])

        return SummaryLayout(
            title="Addons",
            sections=[section],
            conclusion=ConclusionBlock(True, "All done"),
        )

    def to_machine(self, result: "Result[list]") -> dict:
        return {"data": result.data, "warnings": result.warnings}
