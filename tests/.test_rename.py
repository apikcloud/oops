from unittest.mock import MagicMock

import click
import pytest

from oops.commands.submodules import rename as rename_mod
from oops.commands.submodules.rename import main


def _sub(name="org/repo", url="git@github.com:org/repo.git", path=".third-party/org/repo"):
    sub = MagicMock()
    sub.name = name
    sub.url = url
    sub.path = path
    return sub


def _invoke(monkeypatch, repo, **kwargs):
    monkeypatch.setattr(rename_mod, "Repo", lambda: repo)
    monkeypatch.setattr(rename_mod, "get_symlink_map", lambda _: {})
    monkeypatch.setattr(rename_mod, "is_pull_request", lambda _: False)
    defaults = dict(dry_run=False, no_commit=False, prompt=False, force_pr=False, names=())
    main.callback(**{**defaults, **kwargs})


def test_no_gitmodules(monkeypatch):
    repo = MagicMock()
    repo.submodules = []
    monkeypatch.setattr(rename_mod, "Repo", lambda: repo)

    with pytest.raises(click.UsageError, match="No .gitmodules found."):
        main.callback(dry_run=False, no_commit=False, prompt=False, force_pr=False, names=())


def test_no_rename_when_name_unchanged(monkeypatch):
    sub = _sub(name="org/repo")
    repo = MagicMock()
    repo.submodules = [sub]
    monkeypatch.setattr(rename_mod, "desired_path", lambda *a, **kw: "org/repo")

    _invoke(monkeypatch, repo, no_commit=True)

    sub.rename.assert_not_called()


def test_renames_submodule_and_commits(monkeypatch):
    sub = _sub(name="old-name")
    repo = MagicMock()
    repo.submodules = [sub]
    repo.index.diff.return_value = [MagicMock()]
    monkeypatch.setattr(rename_mod, "desired_path", lambda *a, **kw: "org/repo")

    _invoke(monkeypatch, repo)

    sub.rename.assert_called_once_with("org/repo")
    repo.index.commit.assert_called_once()


def test_dry_run_skips_rename_and_commit(monkeypatch):
    sub = _sub(name="old-name")
    repo = MagicMock()
    repo.submodules = [sub]
    monkeypatch.setattr(rename_mod, "desired_path", lambda *a, **kw: "org/repo")

    _invoke(monkeypatch, repo, dry_run=True)

    sub.rename.assert_not_called()
    repo.index.commit.assert_not_called()


def test_no_commit_skips_commit(monkeypatch):
    sub = _sub(name="old-name")
    repo = MagicMock()
    repo.submodules = [sub]
    monkeypatch.setattr(rename_mod, "desired_path", lambda *a, **kw: "org/repo")

    _invoke(monkeypatch, repo, no_commit=True)

    sub.rename.assert_called_once_with("org/repo")
    repo.index.commit.assert_not_called()


def test_rename_error_raises_usage_error(monkeypatch):
    sub = _sub(name="old-name")
    sub.rename.side_effect = Exception("git error")
    repo = MagicMock()
    repo.submodules = [sub]
    monkeypatch.setattr(rename_mod, "desired_path", lambda *a, **kw: "org/repo")

    with pytest.raises(click.UsageError, match="Error renaming submodule old-name"):
        _invoke(monkeypatch, repo)


def test_names_filter(monkeypatch):
    sub1 = _sub(name="org/repo1")
    sub2 = _sub(name="org/repo2")
    repo = MagicMock()
    repo.submodules = [sub1, sub2]
    monkeypatch.setattr(rename_mod, "desired_path", lambda *a, **kw: "org/new-name")

    _invoke(monkeypatch, repo, no_commit=True, names=("org/repo1",))

    sub1.rename.assert_called_once_with("org/new-name")
    sub2.rename.assert_not_called()
