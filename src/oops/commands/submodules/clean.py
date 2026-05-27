# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: clean.py — oops/commands/submodules/clean.py

"""Interactive panel-driven cleanup of submodule base directories.

Walks through (1) confirming the cleanup, (2) picking a reset target from
the last 20 commits, and (3) a final confirmation. Then hard-resets HEAD to
the chosen commit, wipes every configured submodule base directory, and
re-runs ``git submodule update --init --recursive``.

Aliased as ``oops-i-did-it-again`` for when things have gone sideways.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

import click
from git import Repo
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import AppAbort
from oops.core.logger import live_progress, log
from oops.services.git import require_repository, require_submodules
from oops.utils.render import (
    conclude,
    prompt_confirm,
    prompt_select,
    render_footer,
    render_healder,
    render_panel,
)

_PICKER_COUNT = 20
_HEAD_CHOICE = "HEAD (current) — reset in place"


def _recent_commits(repo: Repo, n: int = _PICKER_COUNT) -> tuple[list[str], list[str]]:
    """Return (display_strings, sha_values) for the last *n* commits.

    First entry is always _HEAD_CHOICE / "HEAD" so users can reset in place.
    """
    choices: list[str] = [_HEAD_CHOICE]
    shas: list[str] = ["HEAD"]
    for c in repo.iter_commits("HEAD", max_count=n):
        subject = c.summary[:60]
        date = datetime.fromtimestamp(c.committed_date).date().isoformat()
        choices.append(f"{c.hexsha[:8]}  {subject:<60}  {date}")
        shas.append(c.hexsha)
    return choices, shas


def _submodule_base_paths(repo_path: Path) -> list[Path]:
    paths = list(config.submodules.old_paths) + [config.submodules.current_path]
    return [repo_path / p for p in paths]


def _wipe_base_dirs(paths: Iterable[Path]) -> list[Path]:
    """Delete each existing base directory; return the ones actually removed."""
    removed: list[Path] = []
    for base_path in paths:
        if base_path.exists():
            shutil.rmtree(base_path)
            removed.append(base_path)
    return removed


def _reinit_submodules(repo: Repo) -> None:
    repo.git.submodule("update", "--init", "--recursive")


@command(name="clean", help=__doc__)
@click.pass_context
def main(ctx):
    render_healder(ctx)

    repo, repo_path = require_repository()
    require_submodules(repo)

    base_paths = _submodule_base_paths(repo_path)

    if not prompt_confirm("Reset and clean submodules?", default=True):
        raise AppAbort()

    choices, shas = _recent_commits(repo)
    render_panel(
        title="Reset target",
        content=f"""
            Pick the commit to reset HEAD to.
            Showing the last {_PICKER_COUNT} commits.
            Choose [bold]{_HEAD_CHOICE}[/] to keep HEAD
            where it is and just wipe + re-init.
        """,
    )
    answer = prompt_select("Reset target:", choices)
    if answer is None:
        raise AppAbort()

    target_sha = shas[choices.index(answer)]

    summary_lines = [f"Reset target : [brand.primary]{target_sha}[/]", ""]
    for p in base_paths:
        status = "[dim]exists[/]" if p.exists() else "[dim](absent)[/]"
        summary_lines.append(f"  wipe : {p.name}  {status}")

    render_panel("Ready to proceed", "\n".join(summary_lines))

    if not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    with live_progress(""):
        repo.head.reset(commit=target_sha, index=True, working_tree=True)

        for path in base_paths:
            if not path.exists():
                continue
            log.info(f"Removing {path.name}…")
            shutil.rmtree(path)

        log.info("git submodule update --init --recursive…")
        _reinit_submodules(repo)

    conclude(True, "Submodules cleaned and re-initialised.")

    render_footer(ctx)
