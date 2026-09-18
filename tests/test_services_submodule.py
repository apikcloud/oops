# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops/services/submodule.py — remove_submodule()."""

from __future__ import annotations

from pathlib import Path

from git import Repo
from oops.services.submodule import remove_submodule


def _init_repo(tmp_path: Path) -> Repo:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)
    with repo.config_writer() as cw:
        cw.set_value("user", "email", "test@test.com")
        cw.set_value("user", "name", "Test")
    (repo_path / "README.md").write_text("init\n")
    repo.index.add([str(repo_path / "README.md")])
    repo.index.commit("init")
    return repo


def _make_upstream_repo(tmp_path: Path, name: str, addon_name: str) -> Path:
    upstream_path = tmp_path / name
    upstream_path.mkdir()
    upstream = Repo.init(upstream_path)
    with upstream.config_writer() as cw:
        cw.set_value("user", "email", "test@test.com")
        cw.set_value("user", "name", "Test")
    addon_dir = upstream_path / addon_name
    addon_dir.mkdir()
    manifest = {"name": addon_name, "author": "OCA (OCA)", "depends": []}
    (addon_dir / "__manifest__.py").write_text(repr(manifest))
    upstream.index.add([addon_name])
    upstream.index.commit("init upstream")
    return upstream_path


def _add_submodule(repo: Repo, upstream_path: Path, rel_path: str) -> None:
    with repo.git.custom_environment(GIT_ALLOW_PROTOCOL="file"):
        repo.git.submodule("add", str(upstream_path), rel_path)


def _commit_all(repo: Repo, message: str) -> None:
    repo.git.add("-A")
    repo.index.commit(message)


def _setup_repo_with_submodule_and_link(tmp_path: Path):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    (repo_path / ".third-party").mkdir()
    upstream_path = _make_upstream_repo(tmp_path, "upstream", "web_widget")
    _add_submodule(repo, upstream_path, ".third-party/web")
    link = repo_path / "web_widget"
    link.symlink_to(repo_path / ".third-party" / "web" / "web_widget")
    _commit_all(repo, "add submodule + link")

    sub = next(iter(repo.submodules))
    return repo, repo_path, sub, link


def test_remove_submodule_without_links_leaves_symlink_tracked(tmp_path):
    """Pins the measured behaviour the whole design rests on: with no links
    passed, `Submodule.remove(force=True)` alone leaves the root symlink
    dangling but still tracked in the index.
    """
    repo, repo_path, sub, link = _setup_repo_with_submodule_and_link(tmp_path)

    remove_submodule(repo, repo_path, sub)

    tracked = repo.git.ls_files("-s", "web_widget")
    assert tracked.startswith("120000")
    assert link.is_symlink()
    assert not link.exists()  # target gone — dangling
    assert not (repo_path / ".third-party" / "web").exists()


def test_remove_submodule_with_links_removes_both(tmp_path):
    """With the link passed, both the symlink and the submodule are fully
    removed — from disk, from the index, and from `.gitmodules`.
    """
    repo, repo_path, sub, link = _setup_repo_with_submodule_and_link(tmp_path)
    sub_name = sub.name

    remove_submodule(repo, repo_path, sub, [link])

    assert repo.git.ls_files("-s", "web_widget") == ""
    assert not link.exists()
    assert not link.is_symlink()
    gitmodules = repo_path / ".gitmodules"
    content = gitmodules.read_text() if gitmodules.exists() else ""
    assert sub_name not in content
    assert not (repo_path / ".git" / "modules" / sub_name).exists()
