# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: common.py — src/oops/commands/pr/common.py

from dataclasses import dataclass
from pathlib import Path

import requests
from git import Repo, Submodule
from oops.core.checks import Check, CheckContext, CheckOutcome
from oops.core.models import Result
from oops.services.git import is_pull_request
from oops.services.github import find_pull_requests
from oops.utils.net import get_public_repo_url, parse_repository_url
from oops_engine.compat import TYPE_CHECKING

if TYPE_CHECKING:
    from git.util import IterableList

CLOSED_STATES = {"closed", "merged"}


@dataclass
class PullRequestCheckContext(CheckContext):
    repo: Repo
    repo_path: Path
    submodules: "IterableList[Submodule]"
    token: str


class CheckPullRequestState(Check[PullRequestCheckContext]):
    name = "check_pr_state"
    label = "Pull request state"

    def _run(self) -> Result[CheckOutcome]:
        candidates = [s for s in self.ctx.submodules if is_pull_request(s)]

        problems: "list[str]" = []
        resolved_any = False

        for submodule in candidates:
            try:
                canonical_url = get_public_repo_url(submodule.url)
            except (ValueError, AttributeError):
                canonical_url = submodule.url or ""

            try:
                branch = submodule.branch_name
            except Exception:
                branch = ""

            if not branch:
                continue

            try:
                _, fork_owner, fork_repo = parse_repository_url(canonical_url)
                prs = find_pull_requests(fork_owner, fork_repo, branch, token=self.ctx.token)
            except (ValueError, requests.RequestException) as exc:
                resolved_any = True
                problems.append(submodule.name)
                self.result.add_error(f"{submodule.name}: could not verify PR status ({exc})")
                continue

            if not prs:
                continue

            resolved_any = True
            for pr in prs:
                if pr.state in CLOSED_STATES:
                    problems.append(submodule.name)
                    self.result.add_error(f"{submodule.name}: PR #{pr.number} is {pr.state}")

        if not resolved_any:
            self.add(active=False, status="skipped")
            return self.result

        if problems:
            self.add(status="failed", items=problems)
        else:
            self.add(status="passed")

        return self.result


CHECKS: "list[type[Check]]" = [
    CheckPullRequestState,
]
