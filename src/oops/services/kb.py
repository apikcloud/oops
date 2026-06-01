from pathlib import Path

from oops.core.exceptions import OopsError
from oops.core.metadata import update_metadata
from oops.core.paths import global_kb_path
from oops.kb.build import parse_kb_timestamp, project_kb_path
from oops.kb.store import KBReader


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
    with KBReader(kb_path) as kb:
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
        with KBReader(project) as kb:
            kb_meta = kb.get_meta()
            project_ts = parse_kb_timestamp(kb_meta.get("generated_at"))

    global_kb = global_kb_path(version)
    if global_kb.exists():
        with KBReader(global_kb) as kb:
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
