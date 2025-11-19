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
    url = url.strip()

    def extract_data(parts: list) -> tuple:
        owner, repo = parts[0], parts[1]
        repo = removesuffix(repo, ".git")
        canonical = f"https://{host}/{owner}/{repo}"

        if owner == "oca":
            owner = owner.upper()

        return canonical, owner, repo

    def get_host_and_path(url):
        # 1) SCP-like SSH form: git@host:owner/repo(.git)?
        m = re.match(r"^(?P<user>[^@]+)@(?P<host>[^:]+):(?P<path>.+)$", url)
        if m:
            host = m.group("host")
            path = m.group("path").lstrip("/")

            return host, path

        # 2) URL-like forms (https, http, ssh, git+ssh)
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()

        if scheme in ("ssh", "git+ssh"):
            host = parsed.hostname or ""
            path = (parsed.path or "").lstrip("/")

            return host, path

        if scheme in ("http", "https", ""):
            # Strip possible credentials from netloc (user:pass@host)
            netloc = parsed.netloc or ""
            host = netloc.split("@")[-1] if netloc else ""
            path = (parsed.path or "").lstrip("/")

            return host, path

        raise ValueError(f"Unsupported URL scheme in: {url}")

    host, path = get_host_and_path(url)
    parts = path.split("/")

    if len(parts) < 2:  # noqa: PLR2004
        raise ValueError(f"Malformed url (missing owner/repo): {url}")
    return extract_data(parts)
