# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — oops/commands/addons/download.py

"""
Download addons from a GitHub repository branch.

Clones the repository over SSH (depth=1) into a temporary directory,
discovers addon directories, and copies them into the current project.
Downloaded addons are added to .gitignore (unless --no-exclude is passed).

If no addon names are given, opens an interactive picker over all available
remote addons. Provide names as positional arguments to skip the picker.
"""

import shutil
import tempfile
from pathlib import Path

import click
import git
from oops.commands.base import command
from oops.core.compat import Optional, Tuple
from oops.core.exceptions import APIError, NotFoundError
from oops.core.logger import live_progress
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import file_updater, find_addons, read_tagged_block
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, require_repository
from oops.utils.net import encode_url
from oops.utils.render import colorize, human_readable


def _build_plan(remote_addons: list, existing_names: set) -> Plan:
    """Build download plan from discovered remote addons — pure data, no I/O."""
    actions = []
    for addon in sorted(remote_addons, key=lambda a: a.technical_name):
        if addon.technical_name in existing_names:
            actions.append(
                PlanAction(label=addon.technical_name, kind="nothing to do", detail="already exists")
            )
        else:
            actions.append(
                PlanAction(
                    label=addon.technical_name,
                    kind="available",
                    data={"path": str(addon.path)},
                )
            )
    return Plan(title="Remote addons", actions=actions)


@command(name="download", help=__doc__)
@click.argument("url")
@click.argument("branch")
@click.argument("names", nargs=-1, required=False)
@click.option("--no-exclude", is_flag=True, default=False, help="Do not add downloaded addons to .gitignore.")
@click.option("--no-commit", is_flag=True, help="Do not commit downloaded addons.")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting.")
def main(url: str, branch: str, names: Tuple[str, ...], no_exclude: bool, no_commit: bool, force: bool) -> None:
    repo, repo_path = require_repository()
    ssh_url = encode_url(url, "ssh")
    requested: Optional[set] = set(names) if names else None

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdir = Path(tmpdirname)

        with live_progress("Cloning remote repository…"):
            try:
                git.Repo.clone_from(ssh_url, str(tmpdir), depth=1, branch=branch)
            except git.GitCommandError as exc:
                raise APIError(f"Clone failed: {exc.stderr.strip()}") from exc

        remote_addons = list(find_addons(tmpdir))

        if requested is not None:
            available_names = {a.technical_name for a in remote_addons}
            missing = requested - available_names
            if missing:
                raise NotFoundError(f"Addon(s) not found in remote: {', '.join(sorted(missing))}")

        existing_names = {p.name for p in repo_path.iterdir()}

        # 1. Build the plan (pure business logic)
        candidates = [a for a in remote_addons if requested is None or a.technical_name in requested]
        plan = _build_plan(candidates, existing_names)

        # 2. Define how to execute one action
        downloaded: list = []

        def apply(action: PlanAction) -> Tuple[str, bool]:
            target = repo_path / action.label
            shutil.copytree(action.data["path"], target)
            downloaded.append(action.label)
            return colorize("downloaded", "green"), True

        # 3. Run the shared scenario (select → present → confirm → apply)
        outer: Result[None] = Result()
        result = run_mutation_workflow(
            plan=plan,
            apply=apply,
            outer=outer,
            title="Downloaded addons",
            force=force,
            select=requested is None,
            select_prompt="Select addon(s) to download: ",
            empty_message="No addons available to download.",
        )

    # 4. Command-specific side effects: .gitignore then commit
    if downloaded and not no_exclude:
        gitignore = repo_path / ".gitignore"
        start_tag = "# oops:addons:start"
        end_tag = "# oops:addons:end"
        block = read_tagged_block(gitignore, start_tag, end_tag)
        existing = {ln.strip() for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("#")}
        merged = "\n".join(sorted(existing | {f"{a}/" for a in downloaded}))
        if file_updater(str(gitignore), merged, start_tag=start_tag, end_tag=end_tag):
            outer.merge(commit_v2(repo, repo_path, [".gitignore"], "addons_ignored", skip_hooks=True))

    if downloaded and not no_commit:
        outer.merge(
            commit_v2(
                repo,
                repo_path,
                downloaded,
                "addons_download",
                names=human_readable(downloaded, sep="\n"),
            )
        )
    elif downloaded:
        outer.add_warning("Don't forget to commit the downloaded addons.")

    # 5. Final render (after commit), non-zero exit on errors
    render_and_raise(result, outer)
