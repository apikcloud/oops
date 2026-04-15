# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Unit tests for the PR placement logic in oops-sub-check."""

from pathlib import PurePosixPath

from oops.io.file import desired_path

PREFIX = ".third-party"
PR_URL = "git@github.com:owner/myrepo.git"


def _expected(url: str = PR_URL) -> PurePosixPath:
    """Return the expected base path for a PR submodule (no suffix)."""
    return PurePosixPath(desired_path(url, pull_request=True, prefix=PREFIX))


def _is_misplaced(actual: str, url: str = PR_URL) -> bool:
    """Reproduce the check_pr logic from submodules/check.py."""
    expected = _expected(url)
    return expected not in PurePosixPath(actual).parents


class TestPRPlacementCheck:
    def test_correct_path_with_suffix(self):
        # .third-party/PRs/owner/myrepo/my_addon — valid
        actual = f"{PREFIX}/PRs/owner/myrepo/my_addon"
        assert not _is_misplaced(actual)

    def test_multiple_suffix_levels(self):
        # deeper nesting still valid as long as expected is an ancestor
        actual = f"{PREFIX}/PRs/owner/myrepo/sub/my_addon"
        assert not _is_misplaced(actual)

    def test_no_suffix_is_misplaced(self):
        # exactly at the expected base — no addon dir → misplaced
        actual = f"{PREFIX}/PRs/owner/myrepo"
        assert _is_misplaced(actual)

    def test_wrong_pr_dir_is_misplaced(self):
        # under a different PRs-like dir
        actual = f"{PREFIX}/pull-requests/owner/myrepo/my_addon"
        assert _is_misplaced(actual)

    def test_under_regular_path_is_misplaced(self):
        # not under PRs at all
        actual = f"{PREFIX}/owner/myrepo/my_addon"
        assert _is_misplaced(actual)

    def test_oca_owner_uppercased(self):
        # OCA repos get their owner uppercased by desired_path
        oca_url = "git@github.com:oca/somerepo.git"
        expected = _expected(oca_url)
        assert "OCA" in str(expected)
        actual = f"{PREFIX}/PRs/OCA/somerepo/my_addon"
        assert not _is_misplaced(actual, url=oca_url)

    def test_oca_lowercase_is_misplaced(self):
        oca_url = "git@github.com:oca/somerepo.git"
        actual = f"{PREFIX}/PRs/oca/somerepo/my_addon"
        assert _is_misplaced(actual, url=oca_url)
