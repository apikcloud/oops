# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: checks.py — src/oops/core/checks.py


from dataclasses import asdict, dataclass, field

from oops.core.compat import Generic, List, Literal, TypeVar
from oops.core.models import Result

CheckStatus = Literal["passed", "failed", "skipped"]

CT = TypeVar("CT", bound="CheckContext")


@dataclass
class CheckOutcome:
    name: str
    label: str
    active: bool = True
    status: CheckStatus = "skipped"
    items: List[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckContext:
    """Base context. Each check family extends this."""

    enabled: "List[str]"


class Check(Generic[CT]):
    """Base class for a single submodule check.

    Subclasses set `name` / `label` and implement `_run()`.
    The base handles the enabled/skipped logic.
    """

    name: str
    label: str

    def __init__(self, ctx: CT) -> None:
        self.ctx = ctx
        self.result: Result[CheckOutcome] = Result()

    @property
    def is_enabled(self) -> bool:
        return self.name in self.ctx.enabled

    def run(self) -> Result[CheckOutcome]:
        if not self.is_enabled:
            self.add(active=False, status="skipped")
            return self.result
        return self._run()

    def _run(self) -> Result[CheckOutcome]:
        raise NotImplementedError

    def _resolve(self, problems: "list[str]", error_tpl: str) -> Result[CheckOutcome]:
        """Common pattern: failed with items+errors if problems, else passed."""

        if problems:
            self.add(status="failed", items=problems)
            for p in problems:
                self.result.add_error(error_tpl.format(item=p))
        else:
            self.add(status="passed")
        return self.result

    def add(self, **kwargs) -> None:
        self.result.data = CheckOutcome(self.name, self.label, **kwargs)
