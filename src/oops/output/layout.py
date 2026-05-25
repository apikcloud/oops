# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: layout.py — src/oops/output/layout.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timezone
from typing import TYPE_CHECKING

from oops.core.compat import Generic, L, List, Literal, Optional

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


@dataclass
class SectionBlock:
    title: str
    panels: List[MetricsPanelBlock]
    tables: List[TableBlock]
    info: Optional[List] = field(default_factory=List)
    warnings: Optional[List] = field(default_factory=List)


@dataclass
class ConclusionBlock:
    status: bool
    message: str


@dataclass
class SummaryLayout:
    title: str
    sections: List[SectionBlock]
    conclusion: ConclusionBlock
    warnings: Optional[List] = field(default_factory=List)


@dataclass
class MetricsLayout:
    title: str
    panels: List[MetricsPanelBlock]
    conclusion: ConclusionBlock
    info: Optional[List] = field(default_factory=List)
    warnings: Optional[List] = field(default_factory=List)


Status = Literal["ok", "warning", "failed"]


@dataclass
class Output(Generic[L]):
    layout: L
    status: Status = "ok"
