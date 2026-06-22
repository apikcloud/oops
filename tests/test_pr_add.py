# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops/commands/pr/add.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.pr.add import main
from oops.core.models import PullRequest

PR_URL = "https://github.com/OCA/mail/pull/4"
HEAD_CLONE_URL = "https://github.com/fork-owner/mail.git"
HEAD_REF = "16.0-my-feature"

REMOTE_ADDONS = ["mail_tracking", "mail_activity_board"]

# These match desired_path(HEAD_CLONE_URL, pull_request=True, prefix=".third-party",
# suffix="mail_tracking")
SUB_NAME = "PRs/fork-owner/mail/mail_tracking"
SUB_PATH_STR = ".third-party/PRs/fork-owner/mail/mail_tracking"


def _make_pr(head_repo_url=HEAD_CLONE_URL, head_ref=HEAD_REF):
    return PullRequest(
        upstream="OCA/mail",
        number=4,
        state="open",
        title="Add mail tracking",
        url=PR_URL,
        head="fork-owner:16.0-my-feature",
        base="OCA:16.0",
        head_repo_url=head_repo_url,
        head_ref=head_ref,
        head_owner="fork-owner",
        head_repo="mail",
    )


def _make_config(force_scheme=None, current_path=".third-party"):
    cfg = MagicMock()
    cfg.submodules.force_scheme = force_scheme
    cfg.submodules.current_path = current_path
    return cfg


def _make_repo():
    repo = MagicMock()
    repo.index.diff.return_value = [MagicMock()]
    repo.index.commit.return_value = MagicMock(hexsha="ab" * 8)
    return repo


def _base_patches(tmp_path, mock_repo=None, pr=None):
    if mock_repo is None:
        mock_repo = _make_repo()
    if pr is None:
        pr = _make_pr()
    return {
        # pr/add.py patches
        "oops.commands.pr.add.require_repository": MagicMock(return_value=(mock_repo, tmp_path)),
        "oops.commands.pr.add.get_pull_request": MagicMock(return_value=pr),
        # submodules/add.py patches (flow runs there)
        "oops.commands.submodules.add.config": _make_config(),
        "oops.commands.submodules.add.list_remote_addons": MagicMock(return_value=REMOTE_ADDONS),
        "oops.commands.submodules.add.read_gitmodules": MagicMock(return_value=MagicMock()),
        "oops.commands.submodules.add.commit_v2": MagicMock(
            return_value=MagicMock(messages=[], warnings=[], errors=[])
        ),
        "oops.commands.submodules.add.create_symlink": MagicMock(return_value=None),
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


def _invoke(tmp_path, args=None, extra_patches=None, pr=None):
    patches = _base_patches(tmp_path, pr=pr)
    if extra_patches:
        patches.update(extra_patches)
    with _apply_patches(patches):
        result = CliRunner().invoke(main, args or [PR_URL, "-f", "--token", "tok"])
    return result, patches


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


class TestBadUrl:
    def test_non_github_host_exits_error(self, tmp_path):
        result, _ = _invoke(tmp_path, args=["https://gitlab.com/OCA/mail/pull/4", "-f", "--token", "tok"])
        assert result.exit_code != 0

    def test_repo_url_exits_error(self, tmp_path):
        result, _ = _invoke(tmp_path, args=["https://github.com/OCA/mail", "-f", "--token", "tok"])
        assert result.exit_code != 0

    def test_tree_url_exits_error(self, tmp_path):
        result, _ = _invoke(tmp_path, args=["https://github.com/OCA/mail/tree/main", "-f", "--token", "tok"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Deleted fork / missing head fields
# ---------------------------------------------------------------------------


class TestMissingHeadRepo:
    def test_missing_head_repo_url_exits_error(self, tmp_path):
        pr = _make_pr(head_repo_url=None, head_ref=HEAD_REF)
        result, _ = _invoke(tmp_path, pr=pr)
        assert result.exit_code != 0

    def test_missing_head_repo_url_mentions_unavailable(self, tmp_path):
        pr = _make_pr(head_repo_url=None, head_ref=HEAD_REF)
        result, _ = _invoke(tmp_path, pr=pr)
        assert "unavailable" in result.output.lower()

    def test_missing_head_ref_exits_error(self, tmp_path):
        pr = _make_pr(head_repo_url=HEAD_CLONE_URL, head_ref=None)
        result, _ = _invoke(tmp_path, pr=pr)
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# get_pull_request called with parsed args
# ---------------------------------------------------------------------------


class TestGitHubFetch:
    def test_get_pull_request_called_with_parsed_args(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.add.get_pull_request"].assert_called_once_with(
            "OCA", "mail", 4, "tok"
        )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_commit_v2_called_with_pr_add_message(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        commit_mock = patches["oops.commands.submodules.add.commit_v2"]
        commit_mock.assert_called_once()
        assert commit_mock.call_args[0][3] == "pr_add"

    def test_commit_v2_called_with_already_staged(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        kwargs = patches["oops.commands.submodules.add.commit_v2"].call_args[1]
        assert kwargs.get("already_staged") is True

    def test_commit_v2_called_with_pr_url_kwarg(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        kwargs = patches["oops.commands.submodules.add.commit_v2"].call_args[1]
        assert kwargs.get("pr_url") == PR_URL

    def test_create_symlink_called_per_addon(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        assert patches["oops.commands.submodules.add.create_symlink"].call_count == len(REMOTE_ADDONS)

    def test_pull_request_true_yields_prs_path(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        commit_mock = patches["oops.commands.submodules.add.commit_v2"]
        path_kwarg = commit_mock.call_args[1].get("path", "")
        assert "PRs" in path_kwarg


# ---------------------------------------------------------------------------
# --no-commit
# ---------------------------------------------------------------------------


class TestNoCommit:
    def test_no_commit_skips_commit_v2(self, tmp_path):
        result, patches = _invoke(tmp_path, args=[PR_URL, "-f", "--token", "tok", "--no-commit"])
        assert result.exit_code == 0, result.output
        patches["oops.commands.submodules.add.commit_v2"].assert_not_called()


# ---------------------------------------------------------------------------
# --addons filter
# ---------------------------------------------------------------------------


class TestAddonsOption:
    def test_addons_option_filters_to_requested(self, tmp_path):
        result, patches = _invoke(
            tmp_path,
            args=[PR_URL, "-f", "--token", "tok", "--addons", "mail_tracking"],
        )
        assert result.exit_code == 0, result.output
        create = patches["oops.commands.submodules.add.create_symlink"]
        called_names = [c.args[0].name for c in create.call_args_list]
        assert "mail_tracking" in called_names
        assert "mail_activity_board" not in called_names


# ---------------------------------------------------------------------------
# --force
# ---------------------------------------------------------------------------


class TestForce:
    def test_force_symlinks_all_addons(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        assert patches["oops.commands.submodules.add.create_symlink"].call_count == len(REMOTE_ADDONS)
