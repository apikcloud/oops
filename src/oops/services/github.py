# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: github.py — oops/services/github.py

import os
import subprocess
import zipfile

import requests
from oops.core.compat import List, Optional, Tuple
from oops.core.config import config
from oops.core.exceptions import APIError
from oops.core.logger import log
from oops.core.models import PullRequest, WorkflowRunInfo
from oops.utils.net import make_json_get


def _get_headers(token: Optional[str]) -> dict:
    """Build HTTP headers for a GitHub API request.

    Args:
        token: GitHub personal access token, or None for unauthenticated requests.

    Returns:
        Dict of HTTP headers including Accept and, if provided, Authorization.
    """

    res = {"Accept": "application/vnd.github+json"}
    if token:
        res["Authorization"] = f"token {token}"
    return res


def _get_api_url(owner: str, repo: str, endpoint: str) -> str:
    """Build a full GitHub REST API URL for a given repository endpoint.

    Args:
        owner: Repository owner (user or organisation).
        repo: Repository name.
        endpoint: API path segment appended after the repo (e.g. "zipball/main").

    Returns:
        Full API URL string.
    """

    return f"{config.github_api}/repos/{owner}/{repo}/{endpoint}"


def fetch_branch_zip(  # noqa: PLR0913
    owner: str,
    repo: str,
    branch: str,
    out_dir: str,
    token: Optional[str] = None,
    extract: bool = True,
) -> Tuple[str, Optional[str]]:
    """Download the latest zipball of a repository branch from GitHub.

    Args:
        owner: Repository owner (user or organisation).
        repo: Repository name.
        branch: Branch name to download.
        out_dir: Local directory where the zip file (and extracted content) will be written.
        token: GitHub personal access token for private repositories. Defaults to None.
        extract: If True, extract the zip after downloading. Defaults to True.

    Returns:
        Tuple of (zip_file_path, extracted_root_dir_or_None). The second element is
        None when extract is False.
    """
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"{repo}-{branch}.zip")

    with requests.get(
        _get_api_url(owner, repo, f"zipball/{branch}"),
        headers=_get_headers(token),
        stream=True,
    ) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    if not extract:
        return zip_path, None

    with zipfile.ZipFile(zip_path) as zf:
        # GitHub zipballs have a single top-level folder like "<repo>-<sha>/"
        top = zf.namelist()[0].split("/")[0] + "/"
        zf.extractall(out_dir)
    extracted_root = os.path.join(out_dir, top.rstrip("/"))
    return zip_path, extracted_root


def get_latest_workflow_run(
    owner: str, repo: str, token: str, branch: Optional[str] = None
) -> Optional[WorkflowRunInfo]:  # pragma: no cover
    """Fetch the most recent GitHub Actions workflow run for a repository.

    Args:
        owner: Repository owner (user or organisation).
        repo: Repository name.
        token: GitHub personal access token.
        branch: If provided, filter runs to this branch. Defaults to None.

    Returns:
        WorkflowRunInfo for the latest run, or None if parsing fails.
    """

    params = {"per_page": "1"}
    if branch:
        params["branch"] = branch

    response = make_json_get(
        _get_api_url(owner, repo, "actions/runs"),
        headers=_get_headers(token),
        params=params,
    )

    data = response["workflow_runs"][0]

    try:
        res = WorkflowRunInfo.from_dict(data)
    except Exception as e:
        log.error(f"Could not parse workflow run data: {e}")
        return None

    return res


def get_github_user(name: str) -> str:
    """Return an HTML fragment showing a GitHub user's avatar linked to their profile.

    Args:
        name: GitHub username (e.g. ``"alice"``).

    Returns:
        HTML ``<a>`` element wrapping a 32x32 avatar ``<img>``.
    """
    return (
        f"<a href='https://github.com/{name}'>"
        f"<img src='https://github.com/{name}.png' width='32' height='32' alt='{name}'/></a>"
    )


def check_gh() -> None:
    """Verify that gh is installed and reachable. Raises ClickException otherwise."""
    try:
        subprocess.run(["gh", "--version"], check=True, capture_output=True)
    except FileNotFoundError as e:
        raise APIError("gh CLI not found. Install it from https://cli.github.com.") from e
    except subprocess.CalledProcessError as e:
        raise APIError(f"gh --version failed (exit {e.returncode}). Check your gh installation.") from e


def gh(*args: str) -> subprocess.CompletedProcess:
    """Run a gh CLI command, raising ClickException on failure."""
    try:
        return subprocess.run(["gh", *args], check=True)
    except subprocess.CalledProcessError as e:
        raise APIError(f"gh {args[0]} failed (exit {e.returncode})") from e
    except FileNotFoundError as e:
        raise APIError("gh CLI not found. Install it from https://cli.github.com.") from e


def _get_upstream(owner: str, repo: str, session: "requests.Session") -> str:
    """Returns the full_name of the root (source) repository of a fork."""

    r = session.get(f"https://api.github.com/repos/{owner}/{repo}")
    r.raise_for_status()
    data = r.json()

    if not data.get("fork"):
        return data["full_name"]

    return data["source"]["full_name"]


def _find_prs_from_fork_branch(
    fork_owner: str, fork_repo: str, branch: str, session: "requests.Session"
) -> "Tuple[str, List[dict]]":
    """Find all open PRs on the upstream repository from a branch of a fork."""
    upstream = _get_upstream(fork_owner, fork_repo, session)

    r = session.get(
        f"https://api.github.com/repos/{upstream}/pulls",
        params={
            "state": "all",
            "head": f"{fork_owner}:{branch}",
        },
    )
    r.raise_for_status()
    return upstream, r.json()


def list_remote_addons(
    owner: str,
    repo: str,
    branch: str,
    token: str,
) -> List[str]:
    """List addon directory paths in a GitHub repository at a specific branch.

    Uses the Git Trees API (recursive=1) to find every directory that contains
    a ``__manifest__.py`` or ``__openerp__.py`` file, without cloning the repo.

    Args:
        owner: Repository owner (user or organisation).
        repo: Repository name.
        branch: Branch (or commit SHA) to query.
        token: GitHub personal access token. Defaults to None (public repos only).

    Returns:
        Sorted list of relative directory paths (e.g. ``["sale", "account_ext"]``).
    """
    headers = _get_headers(token)
    url = _get_api_url(owner, repo, f"git/trees/{branch}?recursive=1")
    data = make_json_get(url, headers=headers)

    if data.get("truncated"):
        log.warning("Repository tree was truncated by the API; some addons may be missing.")

    addon_dirs: set[str] = set()
    for item in data.get("tree", []):
        if item.get("type") != "blob":
            continue
        path: str = item["path"]
        filename = path.rsplit("/", 1)[-1]
        if filename not in ("__manifest__.py", "__openerp__.py"):
            continue
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent:
            addon_dirs.add(parent)

    return sorted(addon_dirs)


def check_upstream_module(
    owner: str,
    repo: str,
    module_name: str,
    target_version: str,
    token: Optional[str] = None,
) -> dict:
    """Check if module_name exists on target_version branch of owner/repo and find open PRs.

    Returns {"available": bool, "prs": [{"number": int, "url": str, "title": str}]}.
    Never raises — network/auth errors return available=False and prs=[].
    """
    result: dict = {"available": False, "prs": []}

    try:
        addon_dirs = list_remote_addons(owner, repo, target_version, token or "")
        result["available"] = module_name in addon_dirs
    except Exception:
        pass

    try:
        search_url = "https://api.github.com/search/issues"
        q = f"repo:{owner}/{repo} is:pr base:{target_version} {module_name} in:title"
        r = requests.get(
            search_url,
            params={"q": q, "per_page": 10},
            headers=_get_headers(token),
            timeout=config.default_timeout,
        )
        if r.status_code == 200:
            result["prs"] = [
                {"number": item["number"], "url": item["html_url"], "title": item["title"]}
                for item in r.json().get("items", [])
            ]
    except Exception:
        pass

    return result


def get_pull_request(owner: str, repo: str, number: int, token: str) -> PullRequest:
    """Fetch a single pull request by number.

    Returns a PullRequest whose head_repo_url / head_ref identify the PR's head
    (fork) branch, so the caller can add it as a submodule.
    """
    url = _get_api_url(owner, repo, f"pulls/{number}")
    data = make_json_get(url, headers=_get_headers(token))
    return PullRequest.from_dict(data["base"]["repo"]["full_name"], data)


def list_pull_requests(
    owner: str, repo: str, token: "Optional[str]" = None, state: str = "open"
) -> "List[PullRequest]":
    """List pull requests for a repository, following pagination.

    Args:
        owner: Repository owner (user or organisation).
        repo: Repository name.
        token: GitHub personal access token, or None for public repos.
        state: One of "open", "closed", "all".

    Returns:
        All pull requests across every page of the list endpoint.
    """
    upstream = f"{owner}/{repo}"
    headers = _get_headers(token)
    url: "Optional[str]" = _get_api_url(owner, repo, f"pulls?state={state}&per_page=100")

    prs: "List[PullRequest]" = []
    while url:
        r = requests.get(url, headers=headers, timeout=config.default_timeout)
        r.raise_for_status()
        prs.extend(PullRequest.from_dict(upstream, item) for item in r.json())
        url = r.links.get("next", {}).get("url")

    return prs


def find_pull_requests(owner: str, repo: str, branch: str, token: str) -> "Optional[List[PullRequest]]":
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )

    upstream, prs = _find_prs_from_fork_branch(owner, repo, branch, session)

    if not prs:
        return None

    return [PullRequest.from_dict(upstream, pr) for pr in prs]
