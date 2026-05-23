# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: layout.py — src/oops/output/layout.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timezone
from typing import TYPE_CHECKING

from oops.utils.compat import Generic, L, Literal, Optional

if TYPE_CHECKING:
    pass

UTC = timezone.utc


@dataclass
class TableBlock:
    title: str
    columns: list[tuple[str, str, str]]
    rows: list
    counter: Optional[int] = None


@dataclass
class MetricsPanelBlock:
    title: str
    values: list[list[str]]


@dataclass
class SectionBlock:
    title: str
    panels: list[MetricsPanelBlock]
    tables: list[TableBlock]
    info: Optional[list] = field(default_factory=list)
    warnings: Optional[list] = field(default_factory=list)


@dataclass
class ConclusionBlock:
    status: bool
    message: str


@dataclass
class SummaryLayout:
    title: str
    sections: list[SectionBlock]
    conclusion: ConclusionBlock
    warnings: Optional[list] = field(default_factory=list)


Status = Literal["ok", "warning", "failed"]


@dataclass
class Output(Generic[L]):
    layout: L
    status: Status = "ok"
