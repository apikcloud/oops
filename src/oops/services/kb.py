from pathlib import Path

from git import Repo
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.metadata import update_metadata
from oops.services.git import list_submodules
from oops_engine.addons import enrich_addon, find_addons
from oops_engine.build import odoo_core_repo_id, parse_kb_timestamp, project_kb_path
from oops_engine.compat import Dict, List, Set
from oops_engine.identity import local_repo_id
from oops_engine.models import Addon
from oops_engine.paths import global_kb_path
from oops_engine.store import KBReader


def discover_project_addons(repo: Repo, repo_path: Path, allowed_modules: Set[str]) -> List[Addon]:
    """Discover and classify root-level project addons for a KB build.

    Bridges the CLI's git/config-aware discovery (``io.file.find_addons``/
    ``enrich_addon``) into the plain, already-classified ``Addon`` list
    that ``oops_engine.build.build_project_kb()`` expects — the engine itself
    has no dependency on git, submodules, or config.

    Args:
        repo: The local git repository (from ``services.git.require_repository()``).
        repo_path: Repository root.
        allowed_modules: Module names to keep (the user-owned installed list).

    Returns:
        Discovered addons, classified (``.classification`` populated),
        sorted by technical name.
    """
    subs = list_submodules(repo)

    # Deduplicate by resolved real path, preferring root-level symlinks over
    # real files (mirrors commands/addons/list.py's established dedup rule).
    seen: Dict[str, Addon] = {}
    for addon in find_addons(repo_path, shallow=True):
        if addon.path not in seen or addon.symlinked:
            seen[addon.path] = addon

    project_addons = [a for a in seen.values() if a.technical_name in allowed_modules]
    project_addons.sort(key=lambda a: a.technical_name)

    for addon in project_addons:
        sub = subs.get(addon.rel_path, {})
        enrich_addon(addon, sub, author=config.manifest.author, prefix=config.project.prefix, owner=config.github.owner)

    return project_addons


def require_kb(version: str) -> Path:
    """Raise OopsError if the global KB for the given Odoo version does not exist.

    Also writes the KB path into the active command metadata.

    Args:
        version: Odoo major version string (e.g. ``"17"``).

    Returns:
        Path to the global KB directory.
    """
    kb_path = global_kb_path(version)
    if not kb_path.exists():
        raise OopsError("This command requires an initialised global KB")

    update_metadata(kb_global_path=str(kb_path))
    return kb_path


def load_odoo_kb(version: str) -> dict:
    """Read the global KB for the given Odoo version.

    Returns an empty dict if the KB doesn't exist — the command will still
    work, but unresolved warnings will be louder.
    """
    kb_path = global_kb_path(version)
    if not kb_path.exists():
        return {}
    with KBReader(kb_path, repo_ids=[odoo_core_repo_id(version)]) as kb:
        return kb.get_modules()


def set_kb_metadata(repo_path: Path, version: str) -> None:
    """Populate KB timestamp fields on the active command metadata.

    Reads ``generated_at`` from both the project-local KB and the global KB
    and forwards them to :func:`~oops.core.metadata.update_metadata`.

    Args:
        repo_path: Root path of the current Git repository.
        version: Odoo major version string (e.g. ``"17"``).
    """
    project_ts = None
    global_ts = None

    project = project_kb_path(repo_path)
    if project.exists():
        with KBReader(project, repo_ids=[local_repo_id(repo_path), odoo_core_repo_id(version)]) as kb:
            kb_meta = kb.get_meta()
            project_ts = parse_kb_timestamp(kb_meta.get("generated_at"))

    global_kb = global_kb_path(version)
    if global_kb.exists():
        with KBReader(global_kb, repo_ids=[odoo_core_repo_id(version)]) as kb:
            global_ts = parse_kb_timestamp(kb.get_meta().get("generated_at"))

    fields: dict = {}
    if global_kb.exists():
        fields["kb_global_path"] = str(global_kb)
    if project_ts:
        fields["kb_project_ts"] = project_ts
    if global_ts:
        fields["kb_global_ts"] = global_ts
    if fields:
        update_metadata(**fields)
