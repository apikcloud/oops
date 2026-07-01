# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: net.py — oops/utils/net.py

import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from git import Repo
from oops.core.compat import Optional, Tuple
from oops.core.config import config
from oops.utils.helpers import removesuffix


def make_json_get(url: str, headers: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    """Perform an HTTP GET request and return the parsed JSON response.

    Args:
        url: URL to request.
        headers: Optional HTTP headers to include.
        params: Optional query parameters to include.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        requests.HTTPError: If the response status indicates an error.
    """

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


def clean_url(url: str) -> str:
    """Strip credentials from a URL and normalise the scheme to https.

    Args:
        url: Raw URL string, possibly containing user:password@ credentials.

    Returns:
        Cleaned URL using https with credentials removed.
    """

    # Regex to match URLs with credentials
    pattern = re.compile(r"(https?://|http://)([^@]+@)?(.+)")

    # Substitute the matched pattern to remove credentials and ensure https
    cleaned_url = pattern.sub(lambda m: f"https://{m.group(3)}", url)  # noqa: E231

    return cleaned_url


def _parse_url(url: str) -> Tuple[str, str, str, str]:
    """Parse a Git repository URL into its scheme, host, owner, and repo components.

    Supports SCP-style SSH (``git@host:owner/repo``), ``ssh://``, and HTTP(S) forms.

    Args:
        url: Repository URL to parse.

    Returns:
        Tuple of (scheme, host, owner, repo).

    Raises:
        ValueError: If the URL is missing a host or owner/repo path segments.
    """
    url = url.strip()
    host = path = None

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
    repo = removesuffix(repo, ".git")

    return scheme, host, owner, repo


def encode_url(url: str, scheme: str, suffix: bool = True) -> str:
    """Re-encode a GitHub repository URL in a given scheme.

    Args:
        url: Source repository URL in any supported format.
        scheme: Target scheme, either "https" or "ssh".
        suffix: If True, append ".git" to HTTPS URLs. Defaults to True.

    Returns:
        Re-encoded URL string in the requested scheme.

    Raises:
        ValueError: If the scheme is not "https" or "ssh".
    """

    _, host, owner, repo = _parse_url(url)

    if scheme == "https":
        return f"https://{host}/{owner}/{repo}" + (".git" if suffix else "")
    elif scheme == "ssh":
        return f"git@{host}:{owner}/{repo}.git"
    else:
        raise ValueError(f"Unsupported scheme: {scheme}")


def get_public_repo_url(url: str) -> str:
    """Return the public HTTPS URL of a GitHub repository.

    Args:
        url: Repository URL in any supported format (HTTPS or SSH).

    Returns:
        Canonical public HTTPS URL without a .git suffix.
    """
    return encode_url(url, "https", suffix=False)


def parse_repository_url(url: str) -> Tuple[str, str, str]:
    """Parse a GitHub repository URL and return its canonical form with owner and repo.

    Supported formats: HTTPS (with or without .git, with or without branch path),
    SSH (``git@github.com:owner/repo.git``), and ``ssh://`` URLs.

    Args:
        url: GitHub repository URL to parse.

    Returns:
        Tuple of (canonical_https_url, owner, repo). Owner is upper-cased for OCA.

    Raises:
        ValueError: If the URL cannot be parsed or the host is not github.com.
    """

    scheme, host, owner, repo = _parse_url(url)

    if host != "github.com":
        raise ValueError(f"Unsupported host: {host}")

    canonical_url = f"https://{host}/{owner}/{repo}"
    normalized_owner = owner.upper() if owner.lower() == "oca" else owner
    return canonical_url, normalized_owner, repo


def website_to_github_repo(website: Optional[str]) -> Optional[Tuple[str, str]]:
    """Parse a manifest website URL to (owner, repo), or None if not a GitHub URL."""
    if not website:
        return None
    try:
        _, owner, repo = parse_repository_url(website)
        return (owner, repo)
    except Exception:
        return None


def parse_pull_request_url(url: str) -> Tuple[str, str, int]:
    """Parse a GitHub pull-request URL into (owner, repo, number).

    Example: ``https://github.com/OCA/mail/pull/4`` -> ``("OCA", "mail", 4)``.

    Raises:
        ValueError: If the host is not github.com or the path is not /OWNER/REPO/pull/N.
    """
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").split("@")[-1]
    if host != "github.com":
        raise ValueError(f"Unsupported host: {host!r}")
    parts = (parsed.path or "").strip("/").split("/")
    if len(parts) < 4 or parts[2] != "pull" or not parts[3].isdigit():  # noqa: PLR2004
        raise ValueError(f"Not a pull-request URL: {url}")
    return parts[0], parts[1], int(parts[3])


def resolve_clone_target(
    repo: str,
    working_dir: str,
    default_owner: Optional[str] = None,
    force_scheme: Optional[str] = None,
) -> Tuple[str, Path]:
    """Resolve a clone URL and destination path from a repo slug and a working directory.

    Args:
        repo: Repository reference — full URL, ``owner/repo``, or bare repo name.
        working_dir: Base directory into which the repository will be cloned.
            Tilde and relative components are expanded and resolved.
        default_owner: GitHub org or user used to expand a bare repo name.
        force_scheme: URL scheme to enforce (``"ssh"`` or ``"https"``). If ``None``
            or empty, the URL is left as resolved.

    Returns:
        Tuple of ``(clone_url, target_path)`` where ``target_path`` is
        ``<working_dir>/<repo_name>`` as an absolute :class:`~pathlib.Path`.

    Raises:
        ValueError: If the slug cannot be resolved or is not a valid GitHub URL.
    """
    full_url = resolve_repository_url(repo, default_owner=default_owner)
    _, _, repo_name = parse_repository_url(full_url)
    clone_url = encode_url(full_url, force_scheme) if force_scheme else full_url
    target = Path(working_dir).expanduser().resolve() / repo_name
    return clone_url, target


def resolve_repository_url(slug: str, default_owner: Optional[str] = None) -> str:
    """Expand a repository slug into a full URL parseable by ``_parse_url``.

    Accepted forms:

    - Full URL (any scheme supported by ``_parse_url``) — returned unchanged.
    - ``owner/repo`` shorthand → ``https://github.com/owner/repo``.
    - Bare ``repo`` name → ``https://github.com/{default_owner}/repo``.

    Args:
        slug: Repository reference — full URL, owner/repo, or bare repo name.
        default_owner: GitHub org or user used to expand a bare repo name.
            Typically ``config.github.owner``.

    Returns:
        A URL string that can be passed to ``parse_repository_url`` or
        ``encode_url``.

    Raises:
        ValueError: If ``slug`` is a bare repo name and ``default_owner`` is None.
    """
    stripped = slug.strip()
    if "://" in stripped or stripped.startswith("git@"):
        return stripped
    parts = stripped.split("/")
    if len(parts) == 1:
        if not default_owner:
            raise ValueError(
                f"Cannot expand bare repo name {slug!r}: github.owner is not set in config"
            )
        return f"https://github.com/{default_owner}/{parts[0]}"
    if len(parts) == 2:  # noqa: PLR2004
        return f"https://github.com/{parts[0]}/{parts[1]}"
    return stripped


def sparse_clone(remote_url: str, tmpdir: Path, files: list, branch: Optional[str] = None) -> None:
    """Clone a remote repository with sparse checkout limited to specific paths.

    Performs a shallow clone (depth=1) and enables sparse checkout so only
    the listed files or directories are materialised.

    Args:
        remote_url: URL of the remote repository to clone.
        tmpdir: Local directory where the repository will be cloned.
        files: List of file or directory patterns to include in the sparse checkout.
        branch: Branch to clone. If None, clones the remote default branch.
    """
    kwargs = {"depth": 1, "no_checkout": True}
    if branch:
        kwargs["branch"] = branch
    remote_repo = Repo.clone_from(remote_url, str(tmpdir), **kwargs)

    # Enable sparse checkout
    with remote_repo.config_writer() as cw:
        cw.set_value("core", "sparseCheckout", True)

    # Write the list of patterns to .git/info/sparse-checkout
    sparse_file = tmpdir / ".git" / "info" / "sparse-checkout"
    sparse_file.write_text("\n".join(files) + "\n", encoding="utf-8")

    # Perform the actual checkout
    remote_repo.git.checkout("HEAD")
