# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: serializers.py — src/oops/output/serializers.py

# oops/output/serializers.py

from __future__ import annotations

import json
from typing import Any


def to_json_string(data: Any, **kwargs) -> str:
    """Serialize data to a JSON string.

    Single entry point for JSON serialization — `json.dumps` is never
    called directly from a formatter.
    """
    return json.dumps(data, indent=2, ensure_ascii=False, default=str, **kwargs)

    # original commands is:
    # click.echo(json.dumps(payload, indent=2, default=str))
