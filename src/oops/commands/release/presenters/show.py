# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/release/presenters/show.py


from __future__ import annotations

from oops.core.compat import TYPE_CHECKING, Dict, List
from oops.core.exceptions import NotFoundError
from oops.core.models import Release, ReleaseType, Result
from oops.output.layout import ConclusionBlock, MetricsPanelBlock, Output, SimpleSummaryLayout, TableBlock
from oops.utils.render import format_date, render_boolean
from rich.text import Text

if TYPE_CHECKING:
    from oops.output.base import RenderTarget
RELEASE_COLORS = {
    ReleaseType.MAJOR: "bold grey50 on blue",
    ReleaseType.MINOR: "bold grey50 on green",
    ReleaseType.FIX: "bold grey50 on yellow",
    ReleaseType.UNKNOWN: "white on grey50",
}


def rich_release_type(release_type: ReleaseType) -> Text:
    return Text(release_type.value, style=RELEASE_COLORS[release_type])


def prepare_full(result: "Result[List[Release]]", stats: "Result[Dict]", outer: "Result[None]") -> "Output[Dict]":
    if not result.data:
        raise NotFoundError("No releases found.")
    return Output(
        {
            "warnings": outer.warnings,
            "releases": [item.to_dict() for item in result.data],
            "stats": stats.data,
        }
    )


def prepare_summary(
    result: "Result[List[Release]]", stats: "Result[Dict]", outer: "Result[None]"
) -> "Output[SimpleSummaryLayout]":
    releases = result.data
    if not releases:
        raise NotFoundError("No releases found.")

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
                rich_release_type(release.release_type),
                format_date(release.date),
                release.author,
                str(release.commits),
                render_boolean(bool(release.changelog)),
            ]
            for release in releases
        ],
    )

    panel_values = [
        ["From", format_date(stats.data["first_release"])],
        ["To", format_date(stats.data["last_release"])],
        ["Period", f"{stats.data['delta']} day(s)"],
        ["Releases", str(stats.data["total"])],
        ["Commits", str(stats.data["commits"])],
        ["Major", str(stats.data["types"]["major"])],
        ["Minor", str(stats.data["types"]["minor"])],
        ["Fix", str(stats.data["types"]["fix"])],
    ]

    panel = MetricsPanelBlock("Summary", panel_values)

    return Output(
        SimpleSummaryLayout(
            title="Releases Summary",
            table=table,
            panel=panel,
            conclusion=ConclusionBlock(True, "All done"),
            warnings=outer.warnings,
        )
    )


def prepare(
    result: "Result[List[Release]]", stats: "Result[Dict]", outer: "Result[None]", target: RenderTarget
) -> Output:
    if target.audience == "machine":
        return prepare_full(result, stats, outer)
    return prepare_summary(result, stats, outer)
