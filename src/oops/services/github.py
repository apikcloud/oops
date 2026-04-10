# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: github.py — oops/services/github.py

import logging
import os
import subprocess
import zipfile

import click
import requests
from oops.core.config import config
from oops.core.models import WorkflowRunInfo
from oops.utils.compat import Optional, Tuple
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
        logging.error(f"Could not parse workflow run data: {e}")
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
        raise click.ClickException("gh CLI not found. Install it from https://cli.github.com.") from e
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"gh --version failed (exit {e.returncode}). Check your gh installation.") from e


def gh(*args: str) -> subprocess.CompletedProcess:
    """Run a gh CLI command, raising ClickException on failure."""
    try:
        return subprocess.run(["gh", *args], check=True)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"gh {args[0]} failed (exit {e.returncode})") from e
    except FileNotFoundError as e:
        raise click.ClickException("gh CLI not found. Install it from https://cli.github.com.") from e
