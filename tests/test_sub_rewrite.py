"""
Minimal, end-to-end flavored test for 'oops-sub-rewrite'.

We simulate a repo with a .gitmodules pointing to remote URLs and ensure that
your command rewrites submodule paths to '.third-party/<owner>/<repo>'.
No network calls; we only check file transformations & git config.

Assumptions:
- The CLI entry point 'oops-sub-rewrite' accepts '--force' and '--dry-run' flags,
  and a '--commit/--no-commit' switch (default commit on).
- It uses GitPython under the hood but can operate on the filesystem with
  an existing .git and .gitmodules.

Adjust module/function names if they differ in your codebase.
"""

import subprocess
from pathlib import Path

from click.testing import CliRunner

from oops.commands.submodules.rewrite import main


def _run(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def _init_git_repo(repo: Path) -> Path:
    _run(["git", "init", "-q"], repo)
    # minimal identity
    _run(["git", "config", "user.email", "ci@example.com"], repo)
    _run(["git", "config", "user.name", "CI"], repo)
    # add a dummy file
    (repo / "README.md").write_text("# dummy\n")
    _run(["git", "add", "README.md"], repo)
    _run(["git", "commit", "-m", "init"], repo)
    return repo


def _make_local_remote(tmp_path: Path, name: str) -> Path:
    """Create a minimal local git repo to use as a submodule remote."""
    remote = tmp_path / name
    remote.mkdir()
    _run(["git", "init", "-q", "-b", "main"], remote)
    _run(["git", "config", "user.email", "ci@example.com"], remote)
    _run(["git", "config", "user.name", "CI"], remote)
    _run(["git", "config", "receive.denyCurrentBranch", "ignore"], remote)
    (remote / "README.md").write_text(f"# {name}\n")
    _run(["git", "add", "README.md"], remote)
    _run(["git", "commit", "-q", "-m", "init"], remote)
    return remote


def _add_submodule(repo: Path, name: str, path: str, local_remote: Path, github_url: str) -> None:
    """Add a submodule from a local bare repo, then set its URL to the GitHub URL."""
    cmd = [
        "git", "-c", "protocol.file.allow=always",
        "submodule", "add", "-q", "--name", name, str(local_remote), path,
    ]
    _run(cmd, repo)
    # Rewrite the URL to the canonical GitHub URL for testing the rewrite logic
    _run(["git", "config", "-f", ".gitmodules", f"submodule.{name}.url", github_url], repo)
    _run(["git", "config", f"submodule.{name}.url", github_url], repo)
    # Create a symlink pointing into the submodule so get_symlink_map detects it.
    # The raw readlink target must have the submodule path as parent.
    link = repo / f"_link_{name}"
    link.symlink_to(f"{path}/README.md")
    _run(["git", "add", ".gitmodules", str(link)], repo)


def test_sub_rewrite_rewrites_paths(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem():
        repo_path = Path.cwd()
        _init_git_repo(repo_path)

        # Create local bare repos to avoid network calls
        remotes = tmp_path / "remotes"
        remotes.mkdir()
        remote_oca = _make_local_remote(remotes, "server-ux")
        remote_odoo = _make_local_remote(remotes, "odoo")

        _add_submodule(
            repo_path, "server-ux", "addons/server-ux", remote_oca,
            "https://github.com/OCA/server-ux.git",
        )
        _add_submodule(
            repo_path, "hr-holidays", "addons/hr-holidays", remote_odoo,
            "git@github.com:odoo/odoo.git",
        )

        _run(["git", "commit", "-q", "-m", "add submodules"], repo_path)

        pr = runner.invoke(main, ["--dry-run", "--force"])

        assert pr.exit_code == 0, pr.output

        pr = runner.invoke(main, ["--force"])
        assert pr.exit_code == 0, pr.output

        # Verify .gitmodules paths were rewritten
        data = (repo_path / ".gitmodules").read_text()
        assert "path = .third-party/OCA/server-ux" in data
        assert "path = .third-party/odoo/odoo" in data

        # Optional: ensure a commit was created
        log = _run(["git", "log", "-1", "--pretty=%s"], repo_path).stdout.strip()
        assert "chore(submodules): rewrite submodule paths to new scheme" in log
