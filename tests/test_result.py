# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from oops.core.models import Result


class TestResultConstruction:
    def test_defaults(self):
        r: Result[str] = Result()
        assert r.data is None
        assert r.messages == []
        assert r.warnings == []
        assert r.errors == []
        assert r.ok is True

    def test_with_data(self):
        r: Result[int] = Result(data=42)
        assert r.data == 42
        assert r.ok is True

    def test_ok_false_when_errors(self):
        r: Result[str] = Result()
        r.add_error("boom")
        assert r.ok is False

    def test_ok_true_despite_warnings(self):
        r: Result[str] = Result()
        r.add_warning("heads up")
        assert r.ok is True


class TestResultHelpers:
    def test_add_message(self):
        r: Result[None] = Result()
        r.add_message("info")
        assert r.messages == ["info"]

    def test_add_warning(self):
        r: Result[None] = Result()
        r.add_warning("warn")
        assert r.warnings == ["warn"]

    def test_add_error(self):
        r: Result[None] = Result()
        r.add_error("err")
        assert r.errors == ["err"]


class TestResultMerge:
    def test_merge_folds_all_lists(self):
        a: Result[str] = Result(data="a")
        a.add_message("msg-a")
        a.add_warning("warn-a")
        a.add_error("err-a")

        b: Result[str] = Result()
        b.add_message("msg-b")
        b.add_warning("warn-b")
        b.add_error("err-b")

        result = a.merge(b)
        assert result is a
        assert result.messages == ["msg-a", "msg-b"]
        assert result.warnings == ["warn-a", "warn-b"]
        assert result.errors == ["err-a", "err-b"]

    def test_merge_does_not_touch_data(self):
        a: Result[str] = Result(data="original")
        b: Result[str] = Result(data="other")
        a.merge(b)
        assert a.data == "original"

    def test_merge_empty_other_is_noop(self):
        a: Result[str] = Result(data="x")
        a.add_message("m")
        a.merge(Result())
        assert a.messages == ["m"]
        assert a.warnings == []
        assert a.errors == []

    def test_merge_returns_self_for_chaining(self):
        a: Result[str] = Result()
        b: Result[str] = Result()
        assert a.merge(b) is a

    def test_merge_cross_type(self):
        path_result: Result[str] = Result()
        dict_result: Result[dict] = Result(data={"k": 1})
        dict_result.add_warning("w")
        path_result.merge(dict_result)
        assert path_result.warnings == ["w"]
        assert path_result.data is None
