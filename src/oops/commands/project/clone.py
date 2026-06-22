# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: clone.py — oops/commands/project/clone.py

"""
Clone a GitHub repository and initialise its submodules.

Accepts a full URL, an <org>/<repo> shorthand, or a bare <repo> name
(requires github.owner to be set in config). Applies the configured URL
scheme (submodules.force_scheme) before cloning. The repository is cloned
into the directory defined by working_dir in config and its submodules are
initialised recursively.
"""

from __future__ import annotations

from pathlib import Path

import click
from git import GitCommandError, Repo
from oops.commands.base import command
from oops.core.compat import Optional
from oops.core.config import config
from oops.core.exceptions import ConfigError, OopsError
from oops.core.logger import live_progress
from oops.utils.net import resolve_clone_target
from oops.utils.render import conclude, render_panel


def _resolve_target(repo: str) -> tuple[str, Path]:
    if not config.working_dir:
        raise ConfigError("working_dir is not set in config")
    try:
        clone_url, target = resolve_clone_target(
            repo,
            config.working_dir,
            default_owner=config.github.owner,
            force_scheme=config.submodules.force_scheme,
        )
    except ValueError as exc:
        raise OopsError(f"Invalid repository: {exc}") from exc
    if target.exists():
        raise OopsError(f"Destination already exists: {target}")
    return clone_url, target


@command(name="clone", help=__doc__)
@click.argument("repo")
@click.option("--branch", "-b", default=None, help="Branch to clone (default: repository HEAD).")
@click.option(
    "--jobs",
    "-j",
    default=4,
    show_default=True,
    type=click.IntRange(min=1),
    help="Parallel jobs for submodule initialisation.",
)
def main(repo: str, branch: Optional[str], jobs: int) -> None:
    clone_url, target = _resolve_target(repo)

    # Context panel — what is about to happen.
    render_panel(
        "Clone repository",
        "\n".join(
            [
                f"Source      : [brand.primary]{clone_url}[/]",
                f"Destination : {target}",
                f"Branch      : {branch or '[dim](default HEAD)[/]'}",
            ]
        ),
    )

    target.parent.mkdir(parents=True, exist_ok=True)

    # Phase 1 — clone
    with live_progress(f"Cloning {clone_url}…"):
        try:
            clone_kwargs: dict = {}
            if branch:
                clone_kwargs["branch"] = branch
            cloned = Repo.clone_from(clone_url, str(target), **clone_kwargs)
        except GitCommandError as exc:
            raise OopsError(f"Clone failed: {exc}") from exc

    # Phase 2 — submodules (only if any)
    submodule_count = len(cloned.submodules)
    if submodule_count:
        with live_progress(f"Initialising {submodule_count} submodule(s) ({jobs} job(s))…"):
            try:
                cloned.git.submodule("update", "--init", "--recursive", f"--jobs={jobs}")
            except GitCommandError as exc:
                raise OopsError(f"Submodule init failed: {exc}") from exc

    # Single, coherent conclusion.
    detail = f"{submodule_count} submodule(s) initialised" if submodule_count else "no submodules"
    conclude(True, f"Cloned to {target} — {detail}")
