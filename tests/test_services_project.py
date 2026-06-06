"""Tests for oops.services.project primitives."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import git
import pytest
from oops.core.exceptions import APIError
from oops.services.project import copy_project_files, fetch_project_files, find_projects


class TestFindProjects:
    def _make_git_repo(self, base: Path, name: str) -> Path:
        d = base / name
        d.mkdir()
        (d / ".git").mkdir()
        return d

    def test_returns_valid_project(self, tmp_path: Path) -> None:
        proj = self._make_git_repo(tmp_path, "valid")
        for f in ("requirements.txt", "odoo_version.txt", "packages.txt"):
            (proj / f).write_text("")

        result = find_projects(tmp_path)

        assert result == [proj]

    def test_skips_repo_missing_mandatory_file(self, tmp_path: Path) -> None:
        incomplete = self._make_git_repo(tmp_path, "incomplete")
        (incomplete / "requirements.txt").write_text("")
        # missing odoo_version.txt and packages.txt

        result = find_projects(tmp_path)

        assert result == []

    def test_skips_plain_dir(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        for f in ("requirements.txt", "odoo_version.txt", "packages.txt"):
            (plain / f).write_text("")

        result = find_projects(tmp_path)

        assert result == []

    def test_returns_empty_for_nonexistent_working_dir(self, tmp_path: Path) -> None:
        result = find_projects(tmp_path / "does_not_exist")

        assert result == []

    def test_returns_sorted(self, tmp_path: Path) -> None:
        for name in ("zz_proj", "aa_proj"):
            proj = self._make_git_repo(tmp_path, name)
            for f in ("requirements.txt", "odoo_version.txt", "packages.txt"):
                (proj / f).write_text("")

        result = find_projects(tmp_path)

        assert [p.name for p in result] == ["aa_proj", "zz_proj"]


class TestCopyProjectFiles:
    def test_copies_file(self, tmp_path: Path) -> None:
        remote = tmp_path / "remote"
        remote.mkdir()
        local = tmp_path / "local"
        local.mkdir()
        (remote / "Makefile").write_text("all:\n\techo hi\n")

        applied = copy_project_files(remote, ["Makefile"], local)

        assert applied == ["Makefile"]
        assert (local / "Makefile").read_text() == "all:\n\techo hi\n"

    def test_copies_directory(self, tmp_path: Path) -> None:
        remote = tmp_path / "remote"
        (remote / "subdir").mkdir(parents=True)
        (remote / "subdir" / "file.txt").write_text("content")
        local = tmp_path / "local"
        local.mkdir()

        applied = copy_project_files(remote, ["subdir"], local)

        assert applied == ["subdir"]
        assert (local / "subdir" / "file.txt").read_text() == "content"

    def test_skips_missing_remote_file(self, tmp_path: Path) -> None:
        remote = tmp_path / "remote"
        remote.mkdir()
        local = tmp_path / "local"
        local.mkdir()

        applied = copy_project_files(remote, ["nonexistent.txt"], local)

        assert applied == []
        assert not (local / "nonexistent.txt").exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        remote = tmp_path / "remote"
        (remote / "deep" / "nested").mkdir(parents=True)
        (remote / "deep" / "nested" / "file.txt").write_text("hi")
        local = tmp_path / "local"
        local.mkdir()

        applied = copy_project_files(remote, ["deep/nested/file.txt"], local)

        assert applied == ["deep/nested/file.txt"]
        assert (local / "deep" / "nested" / "file.txt").read_text() == "hi"

    def test_returns_only_present_files(self, tmp_path: Path) -> None:
        remote = tmp_path / "remote"
        remote.mkdir()
        local = tmp_path / "local"
        local.mkdir()
        (remote / "present.txt").write_text("here")

        applied = copy_project_files(remote, ["present.txt", "absent.txt"], local)

        assert applied == ["present.txt"]


class TestFetchProjectFiles:
    def test_forwards_args_to_sparse_clone(self, tmp_path: Path) -> None:
        with patch("oops.services.project.sparse_clone") as mock_clone:
            fetch_project_files("https://example.com/repo.git", "main", ["Makefile"], tmp_path)

        mock_clone.assert_called_once_with("https://example.com/repo.git", tmp_path, ["Makefile"], "main")

    def test_wraps_git_error_into_api_error(self, tmp_path: Path) -> None:
        exc = git.GitCommandError("clone", 128)
        exc.stderr = "fatal: repo not found"
        with patch("oops.services.project.sparse_clone", side_effect=exc):
            with pytest.raises(APIError, match="Clone failed"):
                fetch_project_files("https://example.com/repo.git", "main", ["Makefile"], tmp_path)
