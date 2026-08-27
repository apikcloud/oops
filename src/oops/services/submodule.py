# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Service layer for submodule creation without display dependencies."""

from __future__ import annotations

from pathlib import Path

from git import GitCommandError, Repo
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.models import Result
from oops.io.file import create_symlink, desired_path, ensure_parent
from oops.services.git import commit_v2
from oops.services.github import list_remote_addons
from oops.utils.net import encode_url, parse_repository_url
from oops_engine.compat import Optional


def resolve_target(
    url: str,
    repo_path: Path,
    *,
    pull_request: bool = False,
    suffix: Optional[str] = None,
) -> tuple:
    """Return (name, path_str, abs_path) for a submodule. Pure."""
    name = desired_path(url, pull_request=pull_request, suffix=suffix)
    path_str = desired_path(
        url,
        prefix=str(config.submodules.current_path),
        pull_request=pull_request,
        suffix=suffix,
    )
    return name, path_str, repo_path / path_str


def check_target_available(repo_path: Path, name: str, path_str: str) -> None:
    """Raise OopsError if the destination or its .git/modules dir already exists."""
    sub_path = repo_path / path_str
    if sub_path.exists():
        raise OopsError(f"Destination already exists: {path_str}")
    git_modules_dir = repo_path / ".git" / "modules" / name
    if git_modules_dir.exists():
        raise OopsError(f"Git module directory already exists: {git_modules_dir}")


def add_submodule(
    *,
    repo: "Repo",
    repo_path: Path,
    url: str,
    branch: str,
    addons: Optional[str] = None,
    pull_request: bool = False,
    token: str,
    no_commit: bool = False,
    commit_message_name: str = "submodule_add",
    extra_commit_kwargs: Optional[dict] = None,
    remote_addons: Optional[list] = None,
) -> "Result[list]":
    """Create the submodule, symlink selected addons, optionally commit.

    Returns Result whose .data is the list of linked addon names. No rendering.
    Raises OopsError on fatal input/creation errors.
    """
    try:
        _, owner, repo_name = parse_repository_url(url)
        if config.submodules.force_scheme:
            url = encode_url(url, config.submodules.force_scheme)
    except ValueError as exc:
        raise OopsError(str(exc)) from exc

    remote = remote_addons if remote_addons is not None else list_remote_addons(
        owner, repo_name, branch, token
    )

    if addons:
        requested = {a.strip() for a in addons.split(",") if a.strip()}
        not_found = requested - {Path(p).name for p in remote}
        if not_found:
            raise OopsError(f"Addon(s) not found in repository: {', '.join(sorted(not_found))}")
        selected = [p for p in remote if Path(p).name in requested]
    else:
        selected = list(remote)

    suffix = Path(selected[0]).name if (pull_request and selected) else None
    name, path_str, path = resolve_target(url, repo_path, pull_request=pull_request, suffix=suffix)
    check_target_available(repo_path, name, path_str)

    ensure_parent(path)
    try:
        repo.create_submodule(name=name, path=path_str, url=url, branch=branch)
    except GitCommandError as exc:
        raise OopsError(f"Failed to add submodule: {exc}") from exc
    repo.index.add([".gitmodules"])

    linked: list = []
    for rel in selected:
        link_name = create_symlink(path / rel, repo_path, quiet=True)
        if link_name:
            repo.index.add([str(repo_path / link_name)])
            linked.append(Path(rel).name)

    result: Result[list] = Result(linked)
    if no_commit:
        return result

    commit_kwargs: dict = {
        "name": name,
        "url": url,
        "branch": branch,
        "path": path_str,
        "symlinks": len(linked),
    }
    if extra_commit_kwargs:
        commit_kwargs.update(extra_commit_kwargs)
    result.merge(
        commit_v2(repo, repo_path, [], commit_message_name,
                  skip_hooks=True, already_staged=True, **commit_kwargs)
    )
    return result
