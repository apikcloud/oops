import re

from oops.utils.compat import Optional
from oops.utils.net import parse_repository_url


def extract_submodule_name(line: str) -> Optional[str]:
    """Extract submodule name from a ConfigParser section line.

    Args:
        line: Section line like 'submodule "NAME"'

    Returns:
        Submodule name or None if not found
    """
    match = re.search(r'submodule\s+"([^"]+)"', line)
    if match:
        name = match.group(1)
        return name

    return None


def guess_submodule_name(url: str, pull_request: bool = False) -> str:
    """Guess a submodule name from its URL.

    Args:
        url: Repository URL
        pull_request: If True, prefix with "PRs/"

    Returns:
        Suggested submodule name in format "owner/repo" or "PRs/owner/repo"
    """
    _, owner, repo = parse_repository_url(url)

    if owner == "oca":
        owner = owner.upper()

    if pull_request:
        return f"PRs/{owner}/{repo}"

    return f"{owner}/{repo}"
