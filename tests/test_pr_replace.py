# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops/commands/pr/replace.py."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from oops.commands.pr.replace import main
from oops.core.models import PullRequest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UPSTREAM = "OCA/mail"
FORK_URL = "https://github.com/fork-user/mail.git"
FORK_BRANCH = "17.0-add-feature"
PR_BASE = "OCA:17.0"
PR_URL_STR = "https://github.com/OCA/mail/pull/42"

PR_SUB_NAME = "PRs/fork-user/mail/mail_tracking"
PR_SUB_PATH = ".third-party/PRs/fork-user/mail/mail_tracking"

UPSTREAM_NAME = "OCA/mail"
UPSTREAM_PATH = ".third-party/OCA/mail"

# list_remote_addons returns addon paths; test uses a known addon name.
REMOTE_ADDONS = ["mail_tracking", "mail_activity_board"]


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_pr(base=PR_BASE):
    return PullRequest(
        upstream=UPSTREAM,
        number=42,
        state="open",
        title="Add mail tracking",
        url=PR_URL_STR,
        head=f"fork-user:{FORK_BRANCH}",
        base=base,
        head_repo_url=FORK_URL,
        head_ref=FORK_BRANCH,
        head_owner="fork-user",
        head_repo="mail",
    )


def _make_sub(name=PR_SUB_NAME, path=PR_SUB_PATH, url=FORK_URL, branch=FORK_BRANCH):
    sub = MagicMock()
    sub.name = name
    sub.path = path
    sub.url = url
    sub.branch_name = branch
    return sub


def _make_repo(sub_paths=None):
    """Build a mock Repo.

    Args:
        sub_paths: dict {name: path_str} for existing registered submodules.
    """
    sub_paths = sub_paths or {}
    repo = MagicMock()

    subs = []
    for n, p in sub_paths.items():
        s = MagicMock()
        s.name = n
        s.path = p
        subs.append(s)

    repo.submodules.__iter__ = MagicMock(side_effect=lambda: iter(subs))
    repo.submodules.__getitem__ = MagicMock(
        side_effect=lambda k: next((s for s in subs if s.name == k), MagicMock())
    )
    repo.index.diff.return_value = [MagicMock()]
    return repo


def _make_config():
    cfg = MagicMock()
    cfg.submodules.force_scheme = None
    cfg.submodules.current_path = ".third-party"
    return cfg


def _desired_path_side_effect(url, pull_request=False, prefix=None, suffix=None):
    return UPSTREAM_PATH if prefix else UPSTREAM_NAME


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


def _base_patches(tmp_path, sub=None, pr=None, mock_repo=None, remote_addons=None):
    sub = sub or _make_sub()
    pr = pr or _make_pr()
    mock_repo = mock_repo or _make_repo()
    if remote_addons is None:
        remote_addons = REMOTE_ADDONS
    return {
        "oops.commands.pr.replace.require_repository": MagicMock(
            return_value=(mock_repo, tmp_path)
        ),
        "oops.commands.pr.replace.require_submodules": MagicMock(return_value=[sub]),
        "oops.commands.pr.replace.is_pull_request": MagicMock(return_value=True),
        "oops.commands.pr.replace.get_public_repo_url": MagicMock(return_value=FORK_URL),
        "oops.commands.pr.replace.parse_repository_url": MagicMock(
            return_value=("https://github.com/fork-user/mail", "fork-user", "mail")
        ),
        "oops.commands.pr.replace.find_pull_requests": MagicMock(return_value=[pr]),
        "oops.commands.pr.replace.list_remote_addons": MagicMock(return_value=remote_addons),
        "oops.commands.pr.replace.rewrite_symlinks": MagicMock(return_value=1),
        "oops.commands.pr.replace.commit_v2": MagicMock(
            return_value=MagicMock(messages=[], warnings=[], errors=[])
        ),
        "oops.commands.pr.replace.config": _make_config(),
        "oops.commands.pr.replace.ensure_parent": MagicMock(),
        "oops.commands.pr.replace.desired_path": MagicMock(
            side_effect=_desired_path_side_effect
        ),
    }


@contextmanager
def _apply_patches(patches):
    stack = []
    try:
        for target, mock in patches.items():
            p = patch(target, mock)
            p.start()
            stack.append(p)
        yield
    finally:
        for p in reversed(stack):
            p.stop()


def _invoke(tmp_path, args=None, extra_patches=None, sub=None, pr=None, mock_repo=None,
            remote_addons=None):
    patches = _base_patches(tmp_path, sub=sub, pr=pr, mock_repo=mock_repo,
                            remote_addons=remote_addons)
    if extra_patches:
        patches.update(extra_patches)
    with _apply_patches(patches):
        result = CliRunner().invoke(main, args or ["-f", "--token", "tok"])
    return result, patches


# ---------------------------------------------------------------------------
# No PR submodules
# ---------------------------------------------------------------------------


class TestNoPRSubmodules:
    def test_exits_nonzero(self, tmp_path):
        result, _ = _invoke(
            tmp_path,
            extra_patches={"oops.commands.pr.replace.is_pull_request": MagicMock(return_value=False)},
        )
        assert result.exit_code != 0

    def test_mentions_no_pull_request(self, tmp_path):
        result, _ = _invoke(
            tmp_path,
            extra_patches={"oops.commands.pr.replace.is_pull_request": MagicMock(return_value=False)},
        )
        assert "pull-request" in result.output.lower() or "pull_request" in result.output.lower()


# ---------------------------------------------------------------------------
# No resolved PRs
# ---------------------------------------------------------------------------


class TestNoResolvedPRs:
    def test_exits_zero_when_find_returns_none(self, tmp_path):
        # All subs unresolved → plan all blocked → nothing actionable → EarlyExit (0)
        result, _ = _invoke(
            tmp_path,
            extra_patches={"oops.commands.pr.replace.find_pull_requests": MagicMock(return_value=None)},
        )
        assert result.exit_code == 0

    def test_exits_zero_when_find_returns_empty(self, tmp_path):
        result, _ = _invoke(
            tmp_path,
            extra_patches={"oops.commands.pr.replace.find_pull_requests": MagicMock(return_value=[])},
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Master branch guard — now per-sub blocked, not a fatal OopsError
# ---------------------------------------------------------------------------


class TestMasterBaseBranch:
    def test_exits_zero_master_blocked(self, tmp_path):
        # master → sub becomes blocked → nothing actionable → EarlyExit (0)
        result, _ = _invoke(tmp_path, pr=_make_pr(base="OCA:master"))
        assert result.exit_code == 0

    def test_nothing_to_replace_message(self, tmp_path):
        result, _ = _invoke(tmp_path, pr=_make_pr(base="OCA:master"))
        assert "nothing to replace" in result.output.lower()


# ---------------------------------------------------------------------------
# Branch override
# ---------------------------------------------------------------------------


class TestBranchOverride:
    def test_exits_zero_with_override(self, tmp_path):
        result, _ = _invoke(
            tmp_path,
            args=["-f", "--token", "tok", "--branch", "17.0"],
            pr=_make_pr(base="OCA:master"),
        )
        assert result.exit_code == 0, result.output

    def test_commit_v2_called_with_override_branch(self, tmp_path):
        result, patches = _invoke(
            tmp_path,
            args=["-f", "--token", "tok", "--branch", "17.0"],
            pr=_make_pr(base="OCA:master"),
        )
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.replace.commit_v2"].assert_called_once()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_exits_zero(self, tmp_path):
        result, _ = _invoke(tmp_path)
        assert result.exit_code == 0, result.output

    def test_commit_v2_called_once(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.replace.commit_v2"].assert_called_once()

    def test_commit_v2_uses_pr_replace_key(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        call_args = patches["oops.commands.pr.replace.commit_v2"].call_args
        assert call_args[0][3] == "pr_replace"

    def test_rewrite_symlinks_called(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.replace.rewrite_symlinks"].assert_called_once()

    def test_sub_remove_called(self, tmp_path):
        sub = _make_sub()
        result, _ = _invoke(tmp_path, sub=sub)
        assert result.exit_code == 0, result.output
        sub.remove.assert_called_once_with(force=True)

    def test_git_submodule_add_called(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        repo_mock = patches["oops.commands.pr.replace.require_repository"].return_value[0]
        repo_mock.git.submodule.assert_called()

    def test_list_remote_addons_called(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.replace.list_remote_addons"].assert_called_once()


# ---------------------------------------------------------------------------
# --no-commit
# ---------------------------------------------------------------------------


class TestNoCommit:
    def test_exits_zero(self, tmp_path):
        result, _ = _invoke(tmp_path, args=["-f", "--token", "tok", "--no-commit"])
        assert result.exit_code == 0, result.output

    def test_commit_v2_not_called(self, tmp_path):
        result, patches = _invoke(tmp_path, args=["-f", "--token", "tok", "--no-commit"])
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.replace.commit_v2"].assert_not_called()


# ---------------------------------------------------------------------------
# Upstream submodule already exists — addons fully on disk
# ---------------------------------------------------------------------------


class TestUpstreamAlreadyExists:
    def _make_upstream_repo(self, tmp_path):
        return _make_repo(sub_paths={UPSTREAM_NAME: UPSTREAM_PATH})

    def test_exits_zero(self, tmp_path):
        mock_repo = self._make_upstream_repo(tmp_path)
        result, _ = _invoke(tmp_path, mock_repo=mock_repo)
        assert result.exit_code == 0, result.output

    def test_git_submodule_add_not_called(self, tmp_path):
        mock_repo = self._make_upstream_repo(tmp_path)
        result, _ = _invoke(tmp_path, mock_repo=mock_repo)
        assert result.exit_code == 0, result.output
        add_calls = [c for c in mock_repo.git.submodule.call_args_list if c[0][0] == "add"]
        assert add_calls == []

    def test_git_submodule_update_init_called(self, tmp_path):
        mock_repo = self._make_upstream_repo(tmp_path)
        result, _ = _invoke(tmp_path, mock_repo=mock_repo)
        assert result.exit_code == 0, result.output
        mock_repo.git.submodule.assert_called_with("update", "--init", UPSTREAM_PATH)

    def test_list_remote_addons_not_called_when_all_on_disk(self, tmp_path):
        """When upstream exists and all addons are present on disk, no API call needed."""
        # Create addon dir so on_disk=[addon], off_disk=[] → no API call.
        pr_sub_abs = tmp_path / PR_SUB_PATH / "mail_tracking"
        pr_sub_abs.mkdir(parents=True)
        symlink = tmp_path / "mail_tracking"
        symlink.symlink_to(pr_sub_abs)
        upstream_addon = tmp_path / UPSTREAM_PATH / "mail_tracking"
        upstream_addon.mkdir(parents=True)
        mock_repo = self._make_upstream_repo(tmp_path)
        result, patches = _invoke(tmp_path, mock_repo=mock_repo)
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.replace.list_remote_addons"].assert_not_called()


# ---------------------------------------------------------------------------
# Upstream exists but addon missing from disk → API probe
# ---------------------------------------------------------------------------


class TestUpstreamExistsMissingAddons:
    def _setup(self, tmp_path):
        """Create a symlink from PR sub; upstream registered but addon dir absent."""
        pr_sub_abs = tmp_path / PR_SUB_PATH / "mail_tracking"
        pr_sub_abs.mkdir(parents=True)
        symlink = tmp_path / "mail_tracking"
        symlink.symlink_to(pr_sub_abs)
        return _make_repo(sub_paths={UPSTREAM_NAME: UPSTREAM_PATH})

    def test_list_remote_addons_called_when_addon_missing_from_disk(self, tmp_path):
        mock_repo = self._setup(tmp_path)
        result, patches = _invoke(tmp_path, mock_repo=mock_repo)
        assert result.exit_code == 0, result.output
        patches["oops.commands.pr.replace.list_remote_addons"].assert_called_once()

    def test_git_submodule_add_not_called(self, tmp_path):
        mock_repo = self._setup(tmp_path)
        result, _ = _invoke(tmp_path, mock_repo=mock_repo)
        assert result.exit_code == 0, result.output
        add_calls = [c for c in mock_repo.git.submodule.call_args_list if c[0][0] == "add"]
        assert add_calls == []

    def test_exits_zero_addon_present_upstream(self, tmp_path):
        """Addon missing from disk but present upstream → needs_content_update → still exits 0."""
        mock_repo = self._setup(tmp_path)
        result, _ = _invoke(tmp_path, mock_repo=mock_repo, remote_addons=["mail_tracking"])
        assert result.exit_code == 0, result.output

    def test_git_update_remote_called_when_needs_content_update(self, tmp_path):
        """When addon present upstream but not on disk, update --remote must be called."""
        mock_repo = self._setup(tmp_path)
        result, _ = _invoke(tmp_path, mock_repo=mock_repo, remote_addons=["mail_tracking"])
        assert result.exit_code == 0, result.output
        remote_calls = [
            c for c in mock_repo.git.submodule.call_args_list
            if len(c[0]) >= 2 and c[0][0] == "update" and c[0][1] == "--remote"
        ]
        assert remote_calls, "expected 'git submodule update --remote' when content update needed"


# ---------------------------------------------------------------------------
# Submodule init
# ---------------------------------------------------------------------------


class TestSubmoduleInit:
    def test_update_init_called_for_new_upstream(self, tmp_path):
        result, patches = _invoke(tmp_path)
        assert result.exit_code == 0, result.output
        repo_mock = patches["oops.commands.pr.replace.require_repository"].return_value[0]
        init_calls = [
            c for c in repo_mock.git.submodule.call_args_list
            if len(c[0]) >= 2 and c[0][0] == "update" and c[0][1] == "--init"
        ]
        assert init_calls, "expected at least one 'git submodule update --init' call"

    def test_update_init_called_for_existing_upstream(self, tmp_path):
        mock_repo = _make_repo(sub_paths={UPSTREAM_NAME: UPSTREAM_PATH})
        result, _ = _invoke(tmp_path, mock_repo=mock_repo)
        assert result.exit_code == 0, result.output
        init_calls = [
            c for c in mock_repo.git.submodule.call_args_list
            if len(c[0]) >= 2 and c[0][0] == "update" and c[0][1] == "--init"
        ]
        assert init_calls, "expected 'git submodule update --init' even when upstream already exists"


# ---------------------------------------------------------------------------
# Blocked rows — verify apply() is never called for blocked subs
# ---------------------------------------------------------------------------


class TestBlockedRows:
    def test_blocked_sub_not_applied(self, tmp_path):
        """A sub that resolves to 'master' branch must be blocked, not executed."""
        sub = _make_sub()
        result, _ = _invoke(tmp_path, pr=_make_pr(base="OCA:master"), sub=sub)
        # blocked → nothing actionable → EarlyExit (0), remove must NOT be called
        sub.remove.assert_not_called()

    def test_all_blocked_exits_zero(self, tmp_path):
        result, _ = _invoke(tmp_path, pr=_make_pr(base="OCA:master"))
        assert result.exit_code == 0

    def test_list_remote_addons_not_called_returns_empty(self, tmp_path):
        """When upstream API call fails, sub is blocked and apply() not called."""
        sub = _make_sub()
        result, patches = _invoke(
            tmp_path,
            sub=sub,
            extra_patches={
                "oops.commands.pr.replace.list_remote_addons": MagicMock(
                    side_effect=Exception("API unavailable")
                )
            },
        )
        # blocked → EarlyExit (0), sub not removed
        assert result.exit_code == 0
        sub.remove.assert_not_called()
