# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: layout.py — src/oops/output/layout.py

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from datetime import timezone
from typing import TYPE_CHECKING

from oops.core.compat import Generic, L, List, Literal, Optional
from oops.core.models import StatGroup

if TYPE_CHECKING:
    pass

UTC = timezone.utc


@dataclass
class TableBlock:
    title: str
    columns: List[tuple[str, str, str]]
    rows: List
    counter: Optional[int] = None


@dataclass
class MetricsPanelBlock:
    title: str
    values: List[List[str]]


# @dataclass
# class StatsBlock:


@dataclass
class SectionBlock:
    title: str
    panels: List[MetricsPanelBlock]
    tables: List[TableBlock]
    info: Optional[List] = field(default_factory=list)
    warnings: Optional[List] = field(default_factory=list)


@dataclass
class ConclusionBlock:
    status: bool
    message: str


@dataclass
class BaseLayout(ABC):
    title: str
    conclusion: ConclusionBlock


@dataclass
class SummaryLayout(BaseLayout):
    sections: List[SectionBlock]

    # Optional attributes
    info: Optional[List] = field(default_factory=list)
    warnings: Optional[List] = field(default_factory=list)


@dataclass
class SimpleSummaryLayout(BaseLayout):
    panel: MetricsPanelBlock
    table: TableBlock

    # Optional attributes
    info: Optional[List] = field(default_factory=list)
    warnings: Optional[List] = field(default_factory=list)


@dataclass
class MetricsLayout(BaseLayout):
    panels: List[MetricsPanelBlock]

    # Optional attributes
    info: Optional[List] = field(default_factory=list)
    warnings: Optional[List] = field(default_factory=list)


Status = Literal["ok", "warning", "failed"]


@dataclass
class Output(Generic[L]):
    layout: L
    status: Status = "ok"


def statgroup_to_panel(stg: StatGroup) -> MetricsPanelBlock:
    return MetricsPanelBlock(
        title=stg.label,
        values=[[s.label, str(s.value)] for s in stg.stats],
    )
