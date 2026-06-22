# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops/commands/pr/explore.py and oops/services/github.list_pull_requests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.pr.explore import main
from oops.core.models import PullRequest
from oops.services.github import list_pull_requests

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pr_data(number=1, title="[17.0][MIG] some feature", state="open", author="bob"):
    return {
        "number": number,
        "title": title,
        "state": state,
        "merged_at": None,
        "html_url": f"https://github.com/OCA/account/pull/{number}",
        "head": {
            "label": "bob:17.0-some-feature",
            "ref": "17.0-some-feature",
            "repo": {
                "clone_url": "https://github.com/bob/account.git",
                "name": "account",
                "owner": {"login": "bob"},
            },
        },
        "base": {"label": "OCA:17.0"},
        "user": {"login": author},
    }


def _make_pr(number=1, title="[17.0][MIG] some feature", state="open", author="bob"):
    return PullRequest(
        upstream="OCA/account",
        number=number,
        state=state,
        title=title,
        url=f"https://github.com/OCA/account/pull/{number}",
        head="bob:17.0-some-feature",
        base="OCA:17.0",
        head_repo_url="https://github.com/bob/account.git",
        head_ref="17.0-some-feature",
        head_owner="bob",
        head_repo="account",
        author=author,
    )


def _base_patches(prs=None):
    if prs is None:
        prs = [_make_pr()]
    return {
        "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=prs),
        "oops.commands.pr.explore.get_metadata": MagicMock(return_value=MagicMock()),
        "oops.commands.pr.explore._default_filter": MagicMock(return_value=None),
    }


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


def _invoke(args, extra_patches=None):
    patches = _base_patches()
    if extra_patches:
        patches.update(extra_patches)
    with _apply_patches(patches):
        result = CliRunner().invoke(main, args)
    return result, patches


# ---------------------------------------------------------------------------
# PullRequest.from_dict — author field
# ---------------------------------------------------------------------------


class TestPullRequestFromDict:
    def test_author_captured_from_user_login(self):
        data = _make_pr_data(author="alice")
        pr = PullRequest.from_dict("OCA/account", data)
        assert pr.author == "alice"

    def test_author_none_when_user_missing(self):
        data = _make_pr_data()
        del data["user"]
        pr = PullRequest.from_dict("OCA/account", data)
        assert pr.author is None

    def test_author_none_when_user_is_none(self):
        data = _make_pr_data()
        data["user"] = None
        pr = PullRequest.from_dict("OCA/account", data)
        assert pr.author is None


# ---------------------------------------------------------------------------
# list_pull_requests — pagination
# ---------------------------------------------------------------------------


class TestListPullRequestsPagination:
    def _make_response(self, items, next_url=None):
        mock = MagicMock()
        mock.json.return_value = items
        mock.links = {"next": {"url": next_url}} if next_url else {}
        mock.raise_for_status = MagicMock()
        return mock

    def test_single_page(self):
        page1 = [_make_pr_data(1), _make_pr_data(2)]
        resp1 = self._make_response(page1)

        with patch("oops.services.github.requests.get", return_value=resp1):
            prs = list_pull_requests("OCA", "account")

        assert len(prs) == 2
        assert prs[0].number == 1
        assert prs[1].number == 2

    def test_two_pages_concatenated(self):
        page1 = [_make_pr_data(1)]
        page2 = [_make_pr_data(2)]
        resp1 = self._make_response(page1, next_url="https://api.github.com/page2")
        resp2 = self._make_response(page2)

        responses = [resp1, resp2]
        with patch("oops.services.github.requests.get", side_effect=responses):
            prs = list_pull_requests("OCA", "account")

        assert len(prs) == 2
        assert {pr.number for pr in prs} == {1, 2}

    def test_author_set_from_user_field(self):
        page = [_make_pr_data(1, author="carol")]
        resp = self._make_response(page)

        with patch("oops.services.github.requests.get", return_value=resp):
            prs = list_pull_requests("OCA", "account")

        assert prs[0].author == "carol"


# ---------------------------------------------------------------------------
# Repo resolution
# ---------------------------------------------------------------------------


class TestRepoResolution:
    def test_owner_slash_repo_resolves(self):
        result, patches = _invoke(["OCA/account"])
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.explore.list_pull_requests"].assert_called_once()
        call_args = patches["oops.commands.pr.explore.list_pull_requests"].call_args
        assert call_args[0][0] == "OCA"
        assert call_args[0][1] == "account"

    def test_non_github_host_exits_error(self):
        result, _ = _invoke(["https://gitlab.com/OCA/account"])
        assert result.exit_code != 0

    def test_full_github_url_resolves(self):
        result, patches = _invoke(["https://github.com/OCA/account"])
        assert result.exit_code == 0, result.output
        call_args = patches["oops.commands.pr.explore.list_pull_requests"].call_args
        assert call_args[0][0] == "OCA"
        assert call_args[0][1] == "account"


# ---------------------------------------------------------------------------
# Default filter
# ---------------------------------------------------------------------------


class TestDefaultFilter:
    def test_default_filter_applied_from_project_version(self):
        all_prs = [
            _make_pr(1, title="[17.0][MIG] feature a"),
            _make_pr(2, title="[16.0][MIG] old feature"),
            _make_pr(3, title="unrelated PR"),
        ]
        extra = {
            "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=all_prs),
            "oops.commands.pr.explore._default_filter": MagicMock(return_value="[17.0][MIG]"),
        }
        result, _ = _invoke(["OCA/account"], extra_patches=extra)
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "#2" not in result.output
        assert "#3" not in result.output

    def test_default_filter_none_shows_all(self):
        all_prs = [
            _make_pr(1, title="[17.0][MIG] feature a"),
            _make_pr(2, title="unrelated PR"),
        ]
        extra = {
            "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=all_prs),
            "oops.commands.pr.explore._default_filter": MagicMock(return_value=None),
        }
        result, _ = _invoke(["OCA/account"], extra_patches=extra)
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "#2" in result.output


# ---------------------------------------------------------------------------
# Explicit --filter
# ---------------------------------------------------------------------------


class TestExplicitFilter:
    def test_explicit_filter_substring_case_insensitive(self):
        all_prs = [
            _make_pr(1, title="[17.0][MIG] SALE feature"),
            _make_pr(2, title="[17.0][MIG] purchase feature"),
        ]
        extra = {
            "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=all_prs),
            "oops.commands.pr.explore._default_filter": MagicMock(return_value="[17.0][MIG]"),
        }
        result, _ = _invoke(["OCA/account", "--filter", "sale"], extra_patches=extra)
        assert result.exit_code == 0, result.output
        assert "SALE" in result.output
        assert "purchase" not in result.output

    def test_empty_filter_disables_default(self):
        all_prs = [
            _make_pr(1, title="[17.0][MIG] feature"),
            _make_pr(2, title="unrelated PR"),
        ]
        extra = {
            "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=all_prs),
            "oops.commands.pr.explore._default_filter": MagicMock(return_value="[17.0][MIG]"),
        }
        result, _ = _invoke(["OCA/account", "--filter", ""], extra_patches=extra)
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "#2" in result.output


# ---------------------------------------------------------------------------
# --version option
# ---------------------------------------------------------------------------


class TestVersionOption:
    def test_version_sets_mig_filter(self):
        all_prs = [
            _make_pr(1, title="[17.0][MIG] feature"),
            _make_pr(2, title="[16.0][MIG] old"),
        ]
        extra = {
            "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=all_prs),
            "oops.commands.pr.explore._default_filter": MagicMock(return_value=None),
        }
        result, _ = _invoke(["OCA/account", "--version", "17.0"], extra_patches=extra)
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "#2" not in result.output

    def test_filter_overrides_version(self):
        all_prs = [
            _make_pr(1, title="[17.0][MIG] sale feature"),
            _make_pr(2, title="[17.0][MIG] purchase feature"),
        ]
        extra = {
            "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=all_prs),
            "oops.commands.pr.explore._default_filter": MagicMock(return_value=None),
        }
        result, _ = _invoke(
            ["OCA/account", "--version", "17.0", "--filter", "sale"], extra_patches=extra
        )
        assert result.exit_code == 0, result.output
        assert "#1" in result.output
        assert "#2" not in result.output


# ---------------------------------------------------------------------------
# Empty result
# ---------------------------------------------------------------------------


class TestEmptyResult:
    def test_empty_result_exits_zero(self):
        extra = {
            "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=[]),
            "oops.commands.pr.explore._default_filter": MagicMock(return_value=None),
        }
        result, _ = _invoke(["OCA/account"], extra_patches=extra)
        assert result.exit_code == 0

    def test_empty_result_shows_warning(self):
        extra = {
            "oops.commands.pr.explore.list_pull_requests": MagicMock(return_value=[]),
            "oops.commands.pr.explore._default_filter": MagicMock(return_value=None),
        }
        result, _ = _invoke(["OCA/account"], extra_patches=extra)
        assert "No pull requests" in result.output


# ---------------------------------------------------------------------------
# JSON format
# ---------------------------------------------------------------------------


def _parse_json_output(output: str) -> dict:
    """Strip any spinner prefix before the JSON object."""
    idx = output.index("{")
    return json.loads(output[idx:])


class TestJsonFormat:
    def test_json_format_contains_pull_requests_key(self):
        result, _ = _invoke(["OCA/account", "--format", "json"])
        assert result.exit_code == 0, result.output
        data = _parse_json_output(result.output)
        assert "pull_requests" in data

    def test_json_format_pr_has_expected_fields(self):
        result, _ = _invoke(["OCA/account", "--format", "json"])
        assert result.exit_code == 0, result.output
        data = _parse_json_output(result.output)
        pr = data["pull_requests"][0]
        assert "number" in pr
        assert "title" in pr
        assert "author" in pr
