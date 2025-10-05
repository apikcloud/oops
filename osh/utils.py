import ast
import contextlib
import logging
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from osh.compat import PY38, Any, List, Optional, Tuple
from osh.exceptions import ScriptNotFound
from osh.settings import MANIFEST_NAMES


def get_exec_dir():
    """Return the directory where the current script is located."""

    return os.path.dirname(__file__)


def removesuffix(raw, suffix) -> str:
    """Remove suffix from string if present (Python < 3.9 compatible)."""

    # str.removesuffix added in 3.8
    if PY38:
        return raw[: len(raw) - len(suffix)] if raw[-len(suffix) :] == suffix else raw
    return raw.removesuffix(suffix)


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


def clean_string(raw: Any) -> str:
    """Convert a value to a cleaned string (stripped, no trailing spaces)."""

    return str(raw).strip().rstrip() if raw else ""


def str_to_list(raw: str, sep=",") -> list:
    """Convert a separated string to a list of cleaned items."""

    if not raw:
        return []
    return list(filter(bool, (clean_string(item) for item in raw.split(sep))))


def run(
    cmd: list,
    check: bool = True,
    capture: bool = False,
    cwd: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[str]:
    kwargs: dict = dict(text=True, cwd=cwd)
    if capture:
        # assign explicitly to avoid static type checkers inferring incompatible dict value types
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    logging.debug(f"[{name or 'run'}] {' '.join(cmd)}")

    res = subprocess.run(cmd, check=check, **kwargs)
    return res.stdout if capture else None


def run_script(filepath: str, *args: str) -> str:
    """Run a shell script and return its output as a string."""

    path = os.path.join(get_exec_dir(), filepath)
    logging.debug(f"[script] Running script from {path}")

    if not os.path.exists(path):
        raise ScriptNotFound()

    result = subprocess.run([path, *args], capture_output=True, text=True, check=True)
    return result.stdout


def deep_visit(obj, prefix=""):
    """
    Yield flattened (path, value) pairs for recursive inspection.
    Example: 'assets.web.assets_backend[0]' -> '/module/static/...'
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            yield from deep_visit(v, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from deep_visit(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def filter_and_clean(items: List[str]) -> set:
    """Filter and clean text file"""

    def clean(item):
        if "#" not in item:
            return item.strip()

        return item.split("#")[0].strip()

    items = list(filter(lambda item: item and not item.startswith("#"), items))

    return set(map(clean, items))


def parse_text_file(content: str) -> set:
    """Parse Python text file"""

    return filter_and_clean(content.splitlines())


def read_and_parse(path: Path):
    return sorted(parse_text_file(path.read_text()))


def date_from_string(raw: str) -> date:
    """
    Convert an 8-character string in YYYYMMDD format into a datetime.date object.
    """

    if len(raw) != 8:  # noqa: PLR2004
        raise ValueError("The string does not have the correct length to be converted to a date.")

    y, m, d = int(raw[0:4]), int(raw[4:6]), int(raw[6:8])
    return date(y, m, d)


def write_text_file(path: Path, lines: list, new_line: str = "\n", add_final_newline: bool = True):
    content = new_line.join(lines)
    if add_final_newline:
        content += new_line
    path.write_text(content)


def is_pull_request_path(raw: Optional[str]) -> bool:
    """Detect if a submodule path looks like a pull request path."""

    if not raw:
        return False

    return raw.startswith("PRs/") or "pr" in raw.split("/")


def copytree(src: Path, dst: Path, ignore_git: bool = True) -> None:
    """
    Copy src tree to dst. Fails if dst exists.
    """

    def _ignore(_dir, names):
        if not ignore_git:
            return set()
        return {n for n in names if n == ".git"}

    shutil.copytree(src, dst, symlinks=True, ignore=_ignore)


def materialize_symlink(symlink_path: Path, dry_run: bool) -> None:
    """
    Replace a symbolic link that points to a directory with a physical copy of its target.
    """

    if not symlink_path.exists():
        raise ValueError(f"Path not found: {symlink_path}")
    if not symlink_path.is_symlink():
        raise ValueError(f"Not a symlink: {symlink_path}")

    target = symlink_path.resolve(strict=True)
    if not target.is_dir():
        raise ValueError(f"Symlink target is not a directory: {target}")

    parent = symlink_path.parent
    tmp = parent / f".{symlink_path.name}.__osh_materialize_tmp__"

    if tmp.exists():
        raise ValueError(f"Temporary path already exists: {tmp}")

    logging.debug(f"[osh] materialize: {symlink_path} -> {target}")
    logging.debug(f"[osh] tmp copy:   {tmp}")

    if dry_run:
        return

    try:
        copytree(target, tmp)
        # Remove the symlink and atomically replace with the copied tree
        symlink_path.unlink()
        os.replace(tmp, symlink_path)  # atomic on same filesystem
    except Exception as e:
        # Cleanup tmp on failure
        with contextlib.suppress(Exception):
            if tmp.exists():
                shutil.rmtree(tmp)
        raise ValueError(f"Failed to materialize {symlink_path}: {e}") from e


def parse_manifest(filepath: Path) -> dict:
    """
    Parse an Odoo manifest file,
    then safely convert it to a Python dict via ast.literal_eval.
    """
    source = filepath.read_text(encoding="utf-8")

    # Convert the exact dict literal slice to a Python object (safe: literals only).
    manifest = ast.literal_eval(source)
    if not isinstance(manifest, dict):
        logging.error("Parsed manifest is not a dict after literal evaluation.")
        return {}
    return manifest


def load_manifest(addon_dir: Path) -> dict:
    """Return the path to the manifest file in this addon directory."""
    for manifest_name in MANIFEST_NAMES:
        manifest_path = addon_dir / manifest_name
        if manifest_path.is_file():
            return parse_manifest(manifest_path)
    logging.error(f"No Odoo manifest found in {addon_dir}")
    return {}
