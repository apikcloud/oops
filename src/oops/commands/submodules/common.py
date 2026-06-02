# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: common.py — src/oops/commands/submodules/common.py


import configparser
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from git import GitConfigParser, Repo, Submodule
from oops.core.checks import Check, CheckContext, CheckOutcome
from oops.core.compat import TYPE_CHECKING, List
from oops.core.config import config
from oops.core.logger import log
from oops.core.models import Result
from oops.io.file import check_prefix, desired_path
from oops.services.git import is_pull_request
from oops.utils.net import _parse_url

if TYPE_CHECKING:
    from git.util import IterableList


@dataclass
class SubmoduleCheckContext(CheckContext):
    repo: Repo
    repo_path: Path
    submodules: "IterableList[Submodule]"
    symlinks: "List[str]"
    broken_symlinks: "List[str]"
    gitmodules: GitConfigParser


class CheckPath(Check):
    name = "check_path"
    label = "Path convention"

    def _run(self) -> Result[CheckOutcome]:
        problems = [
            s.name for s in self.ctx.submodules if not check_prefix(str(s.path), str(config.submodules.current_path))
        ]
        return self._resolve(problems, f"Submodule not under {config.submodules.current_path}" + ": {item}")


class CheckSymlink(Check):
    name = "check_symlink"
    label = "Unused submodules"

    def _run(self) -> Result[CheckOutcome]:
        # Check if any symlink target mentions this path
        problems = []
        for submodule in self.ctx.submodules:
            if not any(str(submodule.path) in t for t in self.ctx.symlinks):
                problems.append(submodule.name)
        return self._resolve(problems, "Unused submodules (no symlink points to them): {item}")


class CheckBranch(Check):
    name = "check_branch"
    label = "Missing branch"

    def _run(self) -> Result[CheckOutcome]:
        # Check if any symlink target mentions this path
        problems = []
        for submodule in self.ctx.submodules:
            # Check if branch is set in .gitmodules
            # branch_name cen't be used because it returns master if not set
            section = f'submodule "{submodule.name}"'
            try:
                branch = self.ctx.gitmodules.get_value(section, "branch")
                log.debug(f"{submodule.name}: branch = {branch!r}")
            except configparser.NoOptionError:
                problems.append(submodule.name)
        return self._resolve(problems, "Submodules without branch set in .gitmodules: {item}")


class CheckUrlScheme(Check):
    name = "check_url_scheme"
    label = "Wrong URL scheme"

    def _run(self) -> Result[CheckOutcome]:
        # Check if any symlink target mentions this path
        problems = []
        for submodule in self.ctx.submodules:
            # Check URL scheme

            scheme, _, _, _ = _parse_url(submodule.url)

            if config.submodules.force_scheme and config.submodules.force_scheme != scheme:
                problems.append(submodule.name)
        return self._resolve(
            problems, f"Submodules with malformed URL (not {config.submodules.force_scheme})" + ": {item}"
        )


class CheckDeprecatedRepo(Check):
    name = "check_deprecated_repo"
    label = "Deprecated repositories"

    def _run(self) -> Result[CheckOutcome]:
        # Check if any symlink target mentions this path
        problems = []
        for submodule in self.ctx.submodules:
            _, _, owner, repository = _parse_url(submodule.url)
            repository_name = f"{owner}/{repository}"

            # Check deprecated repositories
            if repository_name in config.submodules.deprecated_repositories:
                # problems.append((submodule.name, config.submodules.deprecated_repositories[repository_name]))
                problems.append(submodule.name)
        return self._resolve(problems, "`{item}` must be replaced")


class CheckBrokenSymlink(Check):
    name = "check_broken_symlink"
    label = "Broken symlinks"

    def _run(self) -> Result[CheckOutcome]:
        problems = [str(s) for s in self.ctx.broken_symlinks]
        return self._resolve(problems, "Broken symlink found: {item}")


class CheckPullRequest(Check):
    name = "check_pr"
    label = "Pull request path convention"

    def _run(self) -> Result[CheckOutcome]:
        problems = []
        for submodule in self.ctx.submodules:
            if is_pull_request(submodule):
                # Recalculate expected path via desired_path and compare, ignoring suffix
                try:
                    expected = PurePosixPath(
                        desired_path(
                            submodule.url,
                            pull_request=True,
                            prefix=str(config.submodules.current_path),
                        )
                    )
                    actual = PurePosixPath(submodule.path)
                    # actual must be a child of expected (suffix required — points to a specific addon)
                    if expected not in actual.parents:
                        problems.append(submodule.name)
                except ValueError:
                    self.result.add_warning(f"Could not compute desired path for {submodule.name!r}, skipping check_pr")

                self.result.add_warning(f"PR: {submodule.name}")

        return self._resolve(problems, f"PR submodules not under {config.pull_request_dir}" + ": {item}")


CHECKS: "list[type[Check]]" = [
    CheckPath,
    CheckSymlink,
    CheckBranch,
    CheckUrlScheme,
    CheckDeprecatedRepo,
    CheckBrokenSymlink,
    CheckPullRequest,
]
