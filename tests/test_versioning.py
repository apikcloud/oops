"""Tests for oops/utils/versioning.py and oops/services/github.py."""

import subprocess
from unittest.mock import patch

import pytest
from oops.utils.versioning import (
    get_last_release,
    get_last_tag,
    get_next_releases,
    is_valid_semver,
)

# ---------------------------------------------------------------------------
# is_valid_semver
# ---------------------------------------------------------------------------


class TestIsValidSemver:
    @pytest.mark.parametrize(
        "tag, expected",
        [
            ("v1.2.3", True),
            ("v0.0.0", True),
            ("v10.20.30", True),
            ("1.2.3", False),       # missing 'v'
            ("v1.2", False),        # only 2 parts
            ("v1.2.3.4", False),    # too many parts
            ("vA.B.C", False),      # non-numeric
            ("", False),
        ],
    )
    def test_parametrized(self, tag, expected):
        assert is_valid_semver(tag) is expected


# ---------------------------------------------------------------------------
# get_last_tag
# ---------------------------------------------------------------------------


class TestGetLastTag:
    def test_returns_tag_string(self):
        with patch("oops.utils.versioning.run") as mock_run:
            mock_run.return_value = "v1.2.3\n"
            assert get_last_tag() == "v1.2.3"

    def test_returns_none_on_called_process_error(self):
        with patch("oops.utils.versioning.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(128, "git")
            assert get_last_tag() is None

    def test_returns_none_when_output_empty(self):
        with patch("oops.utils.versioning.run") as mock_run:
            mock_run.return_value = ""
            assert get_last_tag() is None


# ---------------------------------------------------------------------------
# get_last_release
# ---------------------------------------------------------------------------


class TestGetLastRelease:
    def test_returns_semver_tag(self):
        with patch("oops.utils.versioning.get_last_tag", return_value="v1.2.3"):
            assert get_last_release() == "v1.2.3"

    def test_returns_none_when_no_tag(self):
        with patch("oops.utils.versioning.get_last_tag", return_value=None):
            assert get_last_release() is None

    def test_returns_none_when_tag_not_semver(self):
        with patch("oops.utils.versioning.get_last_tag", return_value="release-2025"):
            assert get_last_release() is None

    def test_returns_none_on_exception(self):
        with patch("oops.utils.versioning.get_last_tag", side_effect=Exception("fail")):
            assert get_last_release() is None


# ---------------------------------------------------------------------------
# get_next_releases
# ---------------------------------------------------------------------------


class TestGetNextReleases:
    def test_computes_correct_bumps(self):
        with patch("oops.utils.versioning.get_last_release", return_value="v1.2.3"):
            minor, patch_, major = get_next_releases()
            assert minor == "v1.3.0"
            assert patch_ == "v1.2.4"
            assert major == "v2.0.0"

    def test_raises_when_no_release(self):
        with patch("oops.utils.versioning.get_last_release", return_value=None):
            with pytest.raises(ValueError, match="No valid release"):
                get_next_releases()

    def test_zero_patch(self):
        with patch("oops.utils.versioning.get_last_release", return_value="v0.0.0"):
            minor, patch_, major = get_next_releases()
            assert minor == "v0.1.0"
            assert patch_ == "v0.0.1"
            assert major == "v1.0.0"


# ---------------------------------------------------------------------------
# oops/services/github.py — pure utility functions
# ---------------------------------------------------------------------------


class TestGithubHelpers:
    def test_get_headers_without_token(self):
        from oops.services.github import _get_headers
        headers = _get_headers(None)
        assert headers["Accept"] == "application/vnd.github+json"
        assert "Authorization" not in headers

    def test_get_headers_with_token(self):
        from oops.services.github import _get_headers
        headers = _get_headers("mytoken")
        assert "Authorization" in headers
        assert "mytoken" in headers["Authorization"]

    def test_get_api_url(self):
        from oops.services.github import _get_api_url
        url = _get_api_url("owner", "repo", "zipball/main")
        assert "owner" in url
        assert "repo" in url
        assert "zipball/main" in url
