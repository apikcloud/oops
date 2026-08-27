# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops/commands/pr/check.py and oops/commands/pr/common.py."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import requests
from click.testing import CliRunner
from oops.commands.pr.check import main
from oops.core.models import PullRequest


@dataclass
class FakeSubmodule:
    name: str
    path: str
    url: str
    branch_name: str = "17.0"


def _pr_submodule(name="PRs/fork-owner/mail/mail_tracking", branch_name="17.0"):
    return FakeSubmodule(
        name=name,
        path=f".third-party/{name}",
        url="https://github.com/fork-owner/mail.git",
        branch_name=branch_name,
    )


def _regular_submodule(name="OCA/server-tools"):
    return FakeSubmodule(
        name=name,
        path=f".third-party/{name}",
        url="https://github.com/OCA/server-tools.git",
        branch_name="17.0",
    )


def _make_pr(number=1, state="open"):
    return PullRequest(
        upstream="OCA/mail",
        number=number,
        state=state,
        title="some feature",
        url=f"https://github.com/OCA/mail/pull/{number}",
        head="fork-owner:17.0-some-feature",
        base="OCA:17.0",
    )


def _base_patches(submodules, find_pull_requests_result=None, find_pull_requests_side_effect=None):
    mock_repo = MagicMock()
    find_mock = MagicMock()
    if find_pull_requests_side_effect is not None:
        find_mock.side_effect = find_pull_requests_side_effect
    else:
        find_mock.return_value = find_pull_requests_result
    return {
        "oops.commands.pr.check.require_repository": MagicMock(return_value=(mock_repo, "/repo")),
        "oops.commands.pr.check.require_submodules": MagicMock(return_value=submodules),
        "oops.commands.pr.common.find_pull_requests": find_mock,
    }, find_mock


class _apply_patches:
    def __init__(self, patches):
        self._patches = patches
        self._stack = []

    def __enter__(self):
        for target, mock in self._patches.items():
            p = patch(target, mock)
            p.start()
            self._stack.append(p)
        return self

    def __exit__(self, *_):
        for p in reversed(self._stack):
            p.stop()


def _invoke(submodules, find_pull_requests_result=None, find_pull_requests_side_effect=None, args=None):
    patches, find_mock = _base_patches(
        submodules,
        find_pull_requests_result=find_pull_requests_result,
        find_pull_requests_side_effect=find_pull_requests_side_effect,
    )
    with _apply_patches(patches):
        result = CliRunner().invoke(main, args or ["--token", "tok"])
    return result, find_mock


def _parse_json_output(output: str) -> dict:
    idx = output.index("{")
    obj, _ = json.JSONDecoder().raw_decode(output, idx)
    return obj


class TestNoPrConventionSubmodules:
    def test_no_pr_submodules_exits_zero(self):
        result, _ = _invoke([_regular_submodule()], args=["--token", "tok", "--format", "json"])
        assert result.exit_code == 0, result.output

    def test_no_pr_submodules_is_skipped(self):
        result, _ = _invoke([_regular_submodule()], args=["--token", "tok", "--format", "json"])
        data = _parse_json_output(result.output)
        assert data["data"][0]["status"] == "skipped"


class TestUnresolvedPr:
    def test_pr_submodule_with_no_matching_pr_is_skipped(self):
        result, _ = _invoke(
            [_pr_submodule()], find_pull_requests_result=None, args=["--token", "tok", "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        data = _parse_json_output(result.output)
        assert data["data"][0]["status"] == "skipped"


class TestOpenPr:
    def test_open_pr_passes(self):
        result, _ = _invoke(
            [_pr_submodule()],
            find_pull_requests_result=[_make_pr(state="open")],
            args=["--token", "tok", "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        data = _parse_json_output(result.output)
        assert data["data"][0]["status"] == "passed"


class TestClosedPr:
    def test_closed_pr_fails(self):
        result, _ = _invoke(
            [_pr_submodule()],
            find_pull_requests_result=[_make_pr(number=4, state="closed")],
            args=["--token", "tok", "--format", "json"],
        )
        assert result.exit_code == 1
        data = _parse_json_output(result.output)
        assert data["data"][0]["status"] == "failed"
        assert any("#4 is closed" in e for e in data["errors"])
        assert any("PRs/fork-owner/mail/mail_tracking" in e for e in data["errors"])


class TestMergedPr:
    def test_merged_pr_fails(self):
        result, _ = _invoke(
            [_pr_submodule()],
            find_pull_requests_result=[_make_pr(number=7, state="merged")],
            args=["--token", "tok", "--format", "json"],
        )
        assert result.exit_code == 1
        data = _parse_json_output(result.output)
        assert data["data"][0]["status"] == "failed"
        assert any("#7 is merged" in e for e in data["errors"])


class TestMixedSet:
    def test_mixed_open_and_closed_fails_with_only_closed_item(self):
        open_sub = _pr_submodule(name="PRs/fork-owner/mail/open_addon")
        closed_sub = _pr_submodule(name="PRs/fork-owner/mail/closed_addon")

        # Distinct return values per submodule, resolved in submodule iteration order.
        results = iter([[_make_pr(number=1, state="open")], [_make_pr(number=2, state="closed")]])

        find_mock = MagicMock(side_effect=lambda *a, **k: next(results))
        patches = {
            "oops.commands.pr.check.require_repository": MagicMock(return_value=(MagicMock(), "/repo")),
            "oops.commands.pr.check.require_submodules": MagicMock(return_value=[open_sub, closed_sub]),
            "oops.commands.pr.common.find_pull_requests": find_mock,
        }
        with _apply_patches(patches):
            result = CliRunner().invoke(main, ["--token", "tok", "--format", "json"])

        assert result.exit_code == 1
        data = _parse_json_output(result.output)
        assert data["data"][0]["status"] == "failed"
        assert data["data"][0]["items"] == ["PRs/fork-owner/mail/closed_addon"]
        assert any("#2 is closed" in e for e in data["errors"])
        assert not any("#1" in e for e in data["errors"])


class TestApiError:
    def test_request_exception_fails_and_mentions_submodule(self):
        result, _ = _invoke(
            [_pr_submodule()],
            find_pull_requests_side_effect=requests.RequestException("boom"),
            args=["--token", "tok", "--format", "json"],
        )
        assert result.exit_code == 1
        data = _parse_json_output(result.output)
        assert data["data"][0]["status"] == "failed"
        assert any("PRs/fork-owner/mail/mail_tracking" in e for e in data["errors"])
