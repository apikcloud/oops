# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/release/presenters/show.py


from __future__ import annotations

from oops.core.models import ReleaseType, Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, SimpleSummaryLayout, TableBlock
from oops.utils.render import format_date, render_boolean
from rich.text import Text

RELEASE_COLORS = {
    ReleaseType.MAJOR: "bold grey50 on blue",
    ReleaseType.MINOR: "bold grey50 on green",
    ReleaseType.FIX: "bold grey50 on yellow",
    ReleaseType.UNKNOWN: "white on grey50",
}


def _rich_release_type(release_type: ReleaseType) -> Text:
    return Text(release_type.value, style=RELEASE_COLORS[release_type])


class ShowPresenter(SimplePresenter[dict]):
    def to_machine(self, result: Result[dict]) -> dict:
        data = result.unwrap

        releases = data["releases"]

        return {
            "warnings": result.warnings,
            "releases": [item.to_dict() for item in releases],
            "stats": data["metrics"],
        }

    def to_human(self, result: Result[dict]) -> SimpleSummaryLayout:

        data = result.unwrap

        releases = data["releases"]
        metrics = data["metrics"]

        table = TableBlock(
            title="",
            columns=[
                ("Release", "dim", "left"),
                ("Type", "dim", "center"),
                ("date", "brand.primary", "left"),
                ("Author", "dim", "right"),
                ("Commit(s)", "green", "right"),
                ("Changelog", "dim", "right"),
            ],
            rows=[
                [
                    release.name,
                    _rich_release_type(release.release_type),
                    format_date(release.date),
                    release.author,
                    str(release.commits),
                    render_boolean(bool(release.changelog)),
                ]
                for release in releases
            ],
        )

        panel_values = [
            ["From", format_date(metrics["first_release"])],
            ["To", format_date(metrics["last_release"])],
            ["Period", f"{metrics['delta']} day(s)"],
            ["Releases", str(metrics["total"])],
            ["Commits", str(metrics["commits"])],
            ["Major", str(metrics["types"]["major"])],
            ["Minor", str(metrics["types"]["minor"])],
            ["Fix", str(metrics["types"]["fix"])],
        ]

        panel = MetricsPanelBlock("Summary", panel_values)

        return SimpleSummaryLayout(
            title="Releases Summary",
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(True, "All done"),
            warnings=result.warnings,
            errors=result.errors,
        )
