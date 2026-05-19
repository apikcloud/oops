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

from git import Repo
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import AppAbort
from oops.services.git import require_repository, require_submodules
from oops.utils.render import conclude, get_console, prompt_confirm, prompt_select
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

_ART_PATH = Path(__file__).parent / "clean_art.txt"


def _load_art() -> str:
    return _ART_PATH.read_text(encoding="utf-8").rstrip("\n")


def _build_layout(info: Panel) -> Layout:
    art = _load_art()
    art_lines = art.count("\n") + 1
    art_panel = Panel(Text(art, style="brand.primary"), border_style="dim", padding=(0, 1))
    layout = Layout(size=art_lines + 2)  # +2 for panel border rows
    layout.split_row(
        Layout(art_panel, name="art", ratio=2),
        Layout(info, name="info", ratio=1),
    )
    return layout


_PICKER_COUNT = 20
_HEAD_CHOICE = "HEAD (current)  — reset in place"


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


def _print_step(console: Console, body: str, title: str) -> None:
    console.print(_build_layout(Panel(body, title=title, border_style="dim")))


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


def _run_actions(repo: Repo, target_sha: str, base_paths: list[Path]) -> None:
    with Live(
        Spinner("dots", text=f"Resetting HEAD to {target_sha[:8]}…"),
        refresh_per_second=10,
    ) as live:
        repo.head.reset(commit=target_sha, index=True, working_tree=True)

        for path in base_paths:
            if not path.exists():
                continue
            live.update(Spinner("dots", text=f"Removing {path.name}…"))
            shutil.rmtree(path)

        live.update(Spinner("dots", text="git submodule update --init --recursive…"))
        _reinit_submodules(repo)


@command(name="clean", help=__doc__)
def main():

    repo, repo_path = require_repository()
    require_submodules(repo)

    console = get_console()
    base_paths = _submodule_base_paths(repo_path)

    # Step 1 — intro: art + info side-by-side, printed once
    _print_step(
        console,
        "[bold]Ok buddy, you messed this repo…[/]\n\n"
        "We're about to wipe the submodule base directories and\n"
        "re-initialise them from [italic].gitmodules[/].\n\n"
        "Pick a commit to hard-reset HEAD to first,\n"
        "or keep HEAD where it is and just clean.",
        title="oops submodules clean",
    )
    if not prompt_confirm("Reset and clean submodules?", default=True):
        raise AppAbort()

    # Step 2 — commit picker (no art re-print; plain panel below)
    choices, shas = _recent_commits(repo)
    console.print(
        Panel(
            f"Pick the commit to reset HEAD to.\n\n"
            f"Showing the last {_PICKER_COUNT} commits.\n"
            f"Choose [bold]{_HEAD_CHOICE}[/] to keep HEAD\n"
            "where it is and just wipe + re-init.",
            title="Reset target",
            border_style="dim",
        )
    )
    answer = prompt_select("Reset target:", choices)
    if answer is None:
        raise AppAbort()
    target_sha = shas[choices.index(answer)]

    # Step 3 — final confirm (no art re-print; plain panel below)
    summary_lines = [f"Reset target : [brand.primary]{target_sha}[/]", ""]
    for p in base_paths:
        status = "[dim]exists[/]" if p.exists() else "[dim](absent)[/]"
        summary_lines.append(f"  wipe : {p.name}  {status}")
    console.print(Panel("\n".join(summary_lines), title="Ready to proceed", border_style="dim"))
    if not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    _run_actions(repo, target_sha, base_paths)

    conclude(True, "Submodules cleaned and re-initialised.")
