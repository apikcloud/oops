# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

import json

from oops.core.metadata import Metadata
from oops.core.models import Result
from oops.output.base import SimplePresenter
from oops.output.formatters import JsonFormatter
from oops.output.layout import Output


class _DataPresenter(SimplePresenter[list]):
    def to_data(self, result: Result[list]) -> dict:
        return {"items": result.unwrap}


class TestSimplePresenterContract:
    def test_default_to_machine_envelope(self):
        result: Result[dict] = Result(data={"a": 1})
        result.add_warning("careful")
        result.add_error("boom")

        payload = SimplePresenter().to_machine(result)

        assert set(payload) == {"data", "warnings", "errors"}
        assert payload["data"] == {"a": 1}
        assert payload["warnings"] == ["careful"]
        assert payload["errors"] == ["boom"]

    def test_default_to_machine_empty_lists(self):
        payload = SimplePresenter().to_machine(Result(data=None))

        assert payload == {"data": None, "warnings": [], "errors": []}

    def test_subclass_overrides_only_data(self):
        result: Result[list] = Result(data=[1, 2])
        result.add_warning("w")

        payload = _DataPresenter().to_machine(result)

        assert set(payload) == {"data", "warnings", "errors"}
        assert payload["data"] == {"items": [1, 2]}
        assert payload["warnings"] == ["w"]
        assert payload["errors"] == []

    def test_json_formatter_appends_metadata(self):
        layout = SimplePresenter().to_machine(Result(data={"a": 1}))
        rendered = JsonFormatter().render(Output(layout=layout, metadata=Metadata(command="x")))

        payload = json.loads(rendered)

        assert set(payload) == {"data", "warnings", "errors", "metadata"}
        assert payload["metadata"]["command"] == "x"
