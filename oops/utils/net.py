import re
from urllib.parse import urlparse

import requests

from oops.core.config import config
from oops.utils.compat import Optional, Tuple
from oops.utils.helpers import removesuffix


def make_json_get(url: str, headers: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    """Make a GET request and return the JSON response."""

    options = {}
    if headers:
        options["headers"] = headers
    if params:
        options["params"] = params

    r = requests.get(
        url,
        **options,
        timeout=config.default_timeout,
    )
    r.raise_for_status()

    return r.json()


def clean_url(url):
    """Removes credentials from a URL if present and replaces http with https."""

    # Regex to match URLs with credentials
    pattern = re.compile(r"(https?://|http://)([^@]+@)?(.+)")

    # Substitute the matched pattern to remove credentials and ensure https
    cleaned_url = pattern.sub(lambda m: f"https://{m.group(3)}", url)  # noqa: E231

    return cleaned_url


def _parse_url(url: str) -> Tuple[str, str, str, str]:
    url = url.strip()

    # 1) SCP-like SSH form: git@host:owner/repo(.git)?
    m = re.match(r"^(?P<user>[^@]+)@(?P<host>[^:]+):(?P<path>.+)$", url)
    if m:
        host = m.group("host")
        path = m.group("path").lstrip("/")

        scheme = "ssh"

    # 2) URL-like forms (https, http, ssh, git+ssh)
    else:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()

        if scheme in ("ssh", "git+ssh"):
            host = parsed.hostname or ""
            path = (parsed.path or "").lstrip("/")

        if scheme in ("http", "https", ""):
            # Strip possible credentials from netloc (user:pass@host)
            netloc = parsed.netloc or ""
            host = netloc.split("@")[-1] if netloc else ""
            path = (parsed.path or "").lstrip("/")

    if not host or not path:
        raise ValueError(f"Malformed url (missing host/owner/repo): {url}")

    parts = path.split("/")

    if len(parts) < 2:  # noqa: PLR2004
        raise ValueError(f"Malformed url (missing owner/repo): {url}")

    owner, repo = parts[0], parts[1]
    if owner == "oca":
        owner = owner.upper()
    repo = removesuffix(repo, ".git")

    return scheme, host, owner, repo


def encode_url(url: str, scheme: str, suffix: bool = True) -> str:
    """Encode a GitHub repository URL into the desired scheme (https or ssh)."""

    _, host, owner, repo = _parse_url(url)

    if scheme == "https":
        return f"https://{host}/{owner}/{repo}" + (".git" if suffix else "")
    elif scheme == "ssh":
        return f"git@{host}:{owner}/{repo}.git"
    else:
        raise ValueError(f"Unsupported scheme: {scheme}")


def get_public_repo_url(url: str) -> str:
    """Get the public HTTPS URL of a GitHub repository from any URL format."""
    return encode_url(url, "https", suffix=False)


def parse_repository_url(url: str) -> Tuple[str, str, str]:
    """
    Parse any GitHub URL (HTTPS or SSH) and return:
    (canonical_https_repo_url, owner, repo)

    Supported examples:
      - https://github.com/odoo/odoo
      - https://github.com/odoo/odoo.git
      - http://github.com/odoo/odoo/tree/19.0
      - ssh://git@github.com/odoo/odoo.git
      - git@github.com:odoo/odoo.git
      - git@github.mycorp.local:team/project.git  (GH Enterprise)

    Returns:
      ("https://<host>/<owner>/<repo>", owner, repo)

    Raises:
      ValueError if the URL cannot be parsed into owner/repo.
    """

    scheme, host, owner, repo = _parse_url(url)

    if host != "github.com":
        raise ValueError(f"Unsupported host: {host}")

    return scheme, owner, repo
