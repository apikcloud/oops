from pathlib import Path

from oops.core.exceptions import OopsError
from oops.core.paths import global_kb_path
from oops.kb.store import KBReader


def require_kb(version: str) -> Path:
    kb_path = global_kb_path(version)
    if not kb_path.exists():
        raise OopsError("This command requires an initialised global KB")

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
