"""Tests covering oops/core/models.py, oops/utils/render.py, oops/utils/helpers.py,
oops/services/git.py, and additional oops/io/file.py utility functions."""

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# oops/utils/render.py
# ---------------------------------------------------------------------------


class TestHumanReadableWidth:
    def test_truncates_long_string(self):
        from oops.utils.render import human_readable
        result = human_readable("A" * 100, width=10)
        assert len(result) <= 10 + 3  # placeholder "..." can extend up to 3 chars

    def test_set_joined(self):
        from oops.utils.render import human_readable
        result = human_readable({1, 2})
        assert "1" in result
        assert "2" in result


class TestRenderBoolean:
    def test_true_returns_symbol(self):
        from oops.utils.render import render_boolean
        assert render_boolean(True) != ""

    def test_false_returns_empty(self):
        from oops.utils.render import render_boolean
        assert render_boolean(False) == ""


class TestSanitizeCell:
    def test_collapses_whitespace(self):
        from oops.utils.render import sanitize_cell
        assert sanitize_cell("  hello   world  ") == "hello world"

    def test_returns_empty_for_falsy(self):
        from oops.utils.render import sanitize_cell
        assert sanitize_cell("") == ""
        assert sanitize_cell(None) == ""


class TestRenderMarkdownTable:
    def test_basic_table(self):
        from oops.utils.render import render_markdown_table
        result = render_markdown_table(["Name", "Version"], [["addon_a", "1.0"]])
        assert "Name" in result
        assert "Version" in result
        assert "addon_a" in result
        assert "---" in result


class TestRenderMaintainers:
    def test_renders_html_links(self):
        from oops.utils.render import render_maintainers
        result = render_maintainers({"maintainers": ["alice", "bob"]})
        assert "alice" in result
        assert "bob" in result

    def test_empty_when_no_maintainers(self):
        from oops.utils.render import render_maintainers
        assert render_maintainers({}) == ""


class TestPrintError:
    def test_prints_to_stdout(self, capsys):
        from oops.utils.render import print_error
        print_error("something went wrong")
        out = capsys.readouterr().out
        assert "something went wrong" in out


# ---------------------------------------------------------------------------
# oops/utils/helpers.py
# ---------------------------------------------------------------------------


class TestDeepVisit:
    def test_flat_dict(self):
        from oops.utils.helpers import deep_visit
        result = dict(deep_visit({"a": 1, "b": 2}))
        assert result["a"] == 1
        assert result["b"] == 2

    def test_nested_dict(self):
        from oops.utils.helpers import deep_visit
        result = dict(deep_visit({"x": {"y": 42}}))
        assert result["x.y"] == 42

    def test_list_values(self):
        from oops.utils.helpers import deep_visit
        result = list(deep_visit([10, 20]))
        assert ("[0]", 10) in result
        assert ("[1]", 20) in result

    def test_scalar(self):
        from oops.utils.helpers import deep_visit
        result = list(deep_visit(99))
        assert result == [("", 99)]

    def test_tuple_treated_as_list(self):
        from oops.utils.helpers import deep_visit
        result = list(deep_visit((1, 2)))
        assert ("[0]", 1) in result


class TestFilterAndClean:
    def test_strips_inline_comment(self):
        from oops.utils.helpers import filter_and_clean
        result = filter_and_clean(["package # version pinned"])
        assert "package" in result
        assert any("package" in item and "#" not in item for item in result)

    def test_skips_comment_lines(self):
        from oops.utils.helpers import filter_and_clean
        result = filter_and_clean(["# full comment", "valid_item"])
        assert "valid_item" in result
        assert "# full comment" not in str(result)

    def test_skips_empty_lines(self):
        from oops.utils.helpers import filter_and_clean
        result = filter_and_clean(["", "item"])
        assert "item" in result
        assert "" not in result


class TestStrToListEmpty:
    def test_empty_input_returns_empty_list(self):
        from oops.utils.helpers import str_to_list
        assert str_to_list("") == []
        assert str_to_list(None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# oops/core/models.py
# ---------------------------------------------------------------------------


class TestImageInfo:
    def _make(self, enterprise=False, release=None):
        from oops.core.models import ImageInfo
        return ImageInfo(
            image="apik/odoo:19.0",
            registry="apik",
            repository="odoo",
            major_version=19.0,
            release=release,
            enterprise=enterprise,
        )

    def test_source_property(self):
        img = self._make()
        assert img.source == "apik/odoo"

    def test_edition_enterprise(self):
        assert self._make(enterprise=True).edition == "enterprise"

    def test_edition_community(self):
        assert self._make(enterprise=False).edition == "community"

    def test_age_with_release(self):
        img = self._make(release=date(2020, 1, 1))
        assert img.age >= 0

    def test_age_without_release(self):
        assert self._make(release=None).age is None

    def test_from_raw_dict(self):
        from oops.core.models import ImageInfo
        vals = {
            "image": "apik/odoo:19.0",
            "org": "apik",
            "repo": "odoo",
            "version": "19.0",
            "release": "20250115",
            "edition": "enterprise",
        }
        img = ImageInfo.from_raw_dict(vals)
        assert img.registry == "apik"
        assert img.enterprise is True
        assert img.release == date(2025, 1, 15)


class TestCommitInfo:
    def _make(self):
        from oops.core.models import CommitInfo
        return CommitInfo(
            sha="abc1234",
            author="Alice",
            email="alice@example.com",
            date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            message="feat: add feature",
        )

    def test_age_is_non_negative(self):
        assert self._make().age >= 0

    def test_from_string(self):
        from oops.core.models import CommitInfo
        raw = "abc1234;Alice;alice@example.com;2025-01-15T00:00:00;feat: something"
        ci = CommitInfo.from_string(raw)
        assert ci.sha == "abc1234"
        assert ci.author == "Alice"
        assert "feat: something" in ci.message

    def test_str_representation(self):
        ci = self._make()
        s = str(ci)
        assert "Alice" in s
        assert "abc1234" in s


class TestWorkflowRunInfo:
    def _vals(self):
        return {
            "name": "CI",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "head_sha": "deadbeef",
            "head_branch": "main",
            "created_at": "2025-01-15T12:00:00Z",
            "url": "https://github.com/...",
            "actor": {"login": "alice"},
        }

    def test_from_dict(self):
        from oops.core.models import WorkflowRunInfo
        run = WorkflowRunInfo.from_dict(self._vals())
        assert run.actor == "alice"
        assert run.branch == "main"
        assert run.conclusion == "success"

    def test_age_is_non_negative(self):
        from oops.core.models import WorkflowRunInfo
        run = WorkflowRunInfo.from_dict(self._vals())
        assert run.age >= 0

    def test_str_representation(self):
        from oops.core.models import WorkflowRunInfo
        run = WorkflowRunInfo.from_dict(self._vals())
        s = str(run)
        assert "CI" in s
        assert "alice" in s


class TestAddonInfo:
    def test_symlinked_property_true(self, tmp_path):
        from oops.core.models import AddonInfo
        addon = AddonInfo(
            path=str(tmp_path),
            rel_path="",
            technical_name="my_addon",
            symlink=True,
            root=True,
            author="Acme",
            version="1.0",
            installable=True,
        )
        assert addon.symlinked is True

    def test_symlinked_property_false_not_root(self, tmp_path):
        from oops.core.models import AddonInfo
        addon = AddonInfo(
            path=str(tmp_path),
            rel_path="sub",
            technical_name="my_addon",
            symlink=True,
            root=False,
            author="Acme",
            version="1.0",
            installable=True,
        )
        assert addon.symlinked is False

    def test_from_path_regular_dir(self, tmp_path):
        from oops.core.models import AddonInfo
        addon_dir = tmp_path / "my_addon"
        addon_dir.mkdir()
        manifest = {"author": "Acme", "version": "16.0.1.0.0", "installable": True}
        info = AddonInfo.from_path(addon_dir, tmp_path, manifest)
        assert info.technical_name == "my_addon"
        assert info.symlink is False
        assert info.author == "Acme"


# ---------------------------------------------------------------------------
# oops/services/git.py — pure/simple functions
# ---------------------------------------------------------------------------


class TestReadGitmodules:
    def test_raises_when_no_working_tree(self):
        from oops.services.git import read_gitmodules
        repo = MagicMock()
        repo.working_tree_dir = None
        with pytest.raises(ValueError, match="working tree"):
            read_gitmodules(repo)

    def test_returns_config_parser(self, tmp_path):
        from oops.services.git import read_gitmodules
        # Create a mock repo with a working_tree_dir
        (tmp_path / ".gitmodules").write_text("")
        repo = MagicMock()
        repo.working_tree_dir = str(tmp_path)
        cfg = read_gitmodules(repo)
        assert cfg is not None


class TestIsPullRequest:
    def test_pr_path_returns_true(self):
        from oops.services.git import is_pull_request
        sub = MagicMock()
        sub.path = "PRs/owner/repo"
        sub.name = "PRs/owner/repo"
        assert is_pull_request(sub) is True

    def test_pr_in_name_returns_true(self):
        from oops.services.git import is_pull_request
        sub = MagicMock()
        sub.path = "some/pr/path"
        sub.name = "some/pr/path"
        assert is_pull_request(sub) is True

    def test_regular_path_returns_false(self):
        from oops.services.git import is_pull_request
        sub = MagicMock()
        sub.path = ".third-party/OCA/sale-workflow"
        sub.name = ".third-party/OCA/sale-workflow"
        assert is_pull_request(sub) is False


# ---------------------------------------------------------------------------
# oops/io/file.py — desired_path and additional coverage
# ---------------------------------------------------------------------------


class TestDesiredPath:
    def test_oca_owner_uppercased(self):
        from oops.io.file import desired_path
        result = desired_path("https://github.com/oca/sale-workflow.git")
        assert "OCA" in result

    def test_pull_request_inserts_dir(self):
        from oops.io.file import desired_path
        result = desired_path("https://github.com/acme/repo.git", pull_request=True)
        from oops.core.config import config
        assert config.pull_request_dir in result

    def test_prefix_prepended(self):
        from oops.io.file import desired_path
        result = desired_path("https://github.com/acme/repo.git", prefix=".third-party/")
        assert result.startswith(".third-party")

    def test_suffix_appended(self):
        from oops.io.file import desired_path
        result = desired_path("https://github.com/acme/repo.git", suffix="v16")
        assert result.endswith("v16")


# ---------------------------------------------------------------------------
# oops/utils/net.py — clean_url and make_json_get with options
# ---------------------------------------------------------------------------


class TestCleanUrl:
    def test_strips_credentials(self):
        from oops.utils.net import clean_url
        url = "https://user:token@github.com/org/repo.git"
        result = clean_url(url)
        assert "user" not in result
        assert "token" not in result
        assert "github.com/org/repo.git" in result

    def test_url_without_credentials_unchanged(self):
        from oops.utils.net import clean_url
        url = "https://github.com/org/repo.git"
        result = clean_url(url)
        assert "github.com/org/repo.git" in result


class TestMakeJsonGet:
    def test_passes_headers_and_params(self):
        from unittest.mock import patch, MagicMock
        from oops.utils.net import make_json_get

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        with patch("oops.utils.net.requests.get", return_value=mock_response) as mock_get:
            result = make_json_get(
                "https://example.com/api",
                headers={"Authorization": "Bearer token"},
                params={"per_page": "10"},
            )
            call_kwargs = mock_get.call_args[1]
            assert "headers" in call_kwargs
            assert "params" in call_kwargs
        assert result == {"ok": True}


# ---------------------------------------------------------------------------
# oops/services/git.py — get_local_repo error paths
# ---------------------------------------------------------------------------


class TestGetLocalRepoErrors:
    def test_raises_click_exception_when_not_in_repo(self, tmp_path, monkeypatch):
        import click
        from git import InvalidGitRepositoryError
        from oops.services.git import get_local_repo

        monkeypatch.chdir(tmp_path)
        with patch("oops.services.git.Repo", side_effect=InvalidGitRepositoryError("not a repo")):
            with pytest.raises(click.ClickException, match="Not inside a git repository"):
                get_local_repo()

    def test_raises_click_exception_on_generic_error(self, tmp_path, monkeypatch):
        import click
        from oops.services.git import get_local_repo

        with patch("oops.services.git.Repo", side_effect=RuntimeError("unexpected")):
            with pytest.raises(click.ClickException, match="Error accessing git repository"):
                get_local_repo()

    def test_raises_when_no_working_tree(self):
        import click
        from oops.services.git import get_local_repo

        mock_repo = MagicMock()
        mock_repo.working_tree_dir = None
        with patch("oops.services.git.Repo", return_value=mock_repo):
            with pytest.raises(click.ClickException, match="Not inside a git repository"):
                get_local_repo()


class TestGetSubmoduleSha:
    def test_returns_sha(self):
        from oops.services.git import get_submodule_sha
        repo = MagicMock()
        repo.git.rev_parse.return_value = "deadbeef"
        result = get_submodule_sha(repo, "HEAD", "submodule/path")
        assert result == "deadbeef"

    def test_returns_none_on_exception(self):
        from oops.services.git import get_submodule_sha
        repo = MagicMock()
        repo.git.rev_parse.side_effect = Exception("not found")
        result = get_submodule_sha(repo, "HEAD", "missing")
        assert result is None


class TestGetLastCommit:
    def test_returns_commit_info(self):
        from oops.services.git import get_last_commit
        output = "abc1234;Alice;alice@example.com;2025-01-15T00:00:00;feat: add feature"
        with patch("oops.services.git.run", return_value=output):
            result = get_last_commit()
            assert result is not None
            assert result.sha == "abc1234"
            assert result.author == "Alice"

    def test_returns_none_when_no_output(self):
        from oops.services.git import get_last_commit
        with patch("oops.services.git.run", return_value=""):
            result = get_last_commit()
            assert result is None

    def test_returns_none_on_error(self):
        import subprocess
        from oops.services.git import get_last_commit
        with patch("oops.services.git.run", side_effect=subprocess.CalledProcessError(128, "git")):
            result = get_last_commit()
            assert result is None

    def test_uses_path_argument(self):
        from oops.services.git import get_last_commit
        output = "abc1234;Alice;alice@example.com;2025-01-15T00:00:00;feat: something"
        with patch("oops.services.git.run", return_value=output) as mock_run:
            get_last_commit(path="/some/path")
            cmd = mock_run.call_args[0][0]
            assert "-C" in cmd
            assert "/some/path" in cmd


# ---------------------------------------------------------------------------
# oops/io/file.py — copytree, parse_packages, parse_requirements
# ---------------------------------------------------------------------------


class TestCopytree:
    def test_copies_directory(self, tmp_path):
        from oops.io.file import copytree
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("hello")
        dst = tmp_path / "dst"
        copytree(src, dst)
        assert (dst / "file.txt").read_text() == "hello"

    def test_skips_git_dir(self, tmp_path):
        from oops.io.file import copytree
        src = tmp_path / "src"
        src.mkdir()
        (src / "file.txt").write_text("data")
        (src / ".git").mkdir()
        (src / ".git" / "config").write_text("gitconf")
        dst = tmp_path / "dst"
        copytree(src, dst, ignore_git=True)
        assert not (dst / ".git").exists()
        assert (dst / "file.txt").exists()


class TestParsePackages:
    def test_reads_packages_file(self, tmp_path, monkeypatch):
        from oops.io.file import parse_packages
        from oops.core.config import config
        pkg_file = tmp_path / config.project.file_packages
        pkg_file.write_text("pkg_a\npkg_b\n")
        result = parse_packages(tmp_path)
        assert "pkg_a" in result
        assert "pkg_b" in result
