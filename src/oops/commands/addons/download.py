# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — oops/commands/addons/download.py

"""
Download addons from a GitHub repository branch.

Clones the repository over SSH (depth=1) into a temporary directory,
discovers addon directories, and copies them into the current project.
Downloaded addons are added to .gitignore (unless --no-exclude is passed).
"""

import shutil
import tempfile
from pathlib import Path

import click
import git
from oops.commands.base import command, render_and_exit
from oops.core.compat import Optional
from oops.core.exceptions import APIError
from oops.core.logger import live_progress, log
from oops.core.models import Result
from oops.io.file import file_updater, find_addons, read_tagged_block
from oops.output.formatters import OutputFormatter, SimpleSummaryConsoleFormatter
from oops.services.git import commit_v2, require_repository
from oops.utils.helpers import str_to_list
from oops.utils.net import encode_url

from .presenters.download import DownloadPresenter


@command(name="download", help=__doc__)
@click.argument("url")
@click.argument("branch")
@click.option("--addons", "addons_list", help="Comma-separated addon names to copy (copies all if omitted).")
@click.option("--exclude/--no-exclude", is_flag=True, default=True, help="Add downloaded addons to .gitignore.")
@click.pass_context
def main(ctx, url: str, branch: str, exclude: bool, addons_list: Optional[str] = None):
    formatter: OutputFormatter = SimpleSummaryConsoleFormatter()

    result: Result[dict] = Result({"cmd": f"Download addons from {url}", "rows": []})
    assert result.data is not None

    repo, repo_path = require_repository()
    ssh_url = encode_url(url, "ssh")
    addons = [] if addons_list is None else str_to_list(addons_list)

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdir = Path(tmpdirname)

        with live_progress("Downloading addons…"):
            log.info(f"Cloning {ssh_url} ({branch})…")
            try:
                git.Repo.clone_from(ssh_url, str(tmpdir), depth=1, branch=branch)
            except git.GitCommandError as exc:
                raise APIError(f"Clone failed: {exc.stderr.strip()}") from exc

            for addon in find_addons(tmpdir):
                if addons and addon.technical_name not in addons:
                    continue

                target_path = repo_path / addon.technical_name

                # FIXME: check version before copying
                try:
                    shutil.copytree(addon.path, target_path)
                except FileExistsError:
                    result.add_warning(f"Skipped (already exists): {addon.technical_name}")
                    result.data["rows"].append({"addon": addon.technical_name, "action": "skipped"})
                    continue

                log.info(f"Downloaded {addon.technical_name}")
                result.data["rows"].append({"addon": addon.technical_name, "action": "downloaded"})

    new_addons = [r["addon"] for r in result.data["rows"] if r["action"] == "downloaded"]

    # TODO: do something here...
    # if not new_addons:
    #     raise EarlyExit("No new addons here")

    if new_addons and exclude:
        gitignore = repo_path / ".gitignore"
        start_tag = "# oops:addons:start"
        end_tag = "# oops:addons:end"

        block = read_tagged_block(gitignore, start_tag, end_tag)
        existing = {ln.strip() for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("#")}
        merged = "\n".join(sorted(existing | {f"{a}/" for a in new_addons}))

        if file_updater(str(gitignore), merged, start_tag=start_tag, end_tag=end_tag):
            commit_result = commit_v2(repo, repo_path, [".gitignore"], "addons_ignored", skip_hooks=True)
            result.merge(commit_result)

    output = DownloadPresenter().prepare(result, target=formatter.target)
    render_and_exit(result, formatter, output, "text")
