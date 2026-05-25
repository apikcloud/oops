# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: compat.py — src/oops/utils/compat.py


"""
Centralizes version-sensitive imports for Python 3.7+ compatibility.
Usage: `from oops.utils.compat import Dict, List, Literal, ...`
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping

# ---------------------------------------------------------------------------
# Version flags
# ---------------------------------------------------------------------------

PY37 = sys.version_info >= (3, 7)
PY38 = sys.version_info >= (3, 8)
PY39 = sys.version_info >= (3, 9)
PY310 = sys.version_info >= (3, 10)
PY311 = sys.version_info >= (3, 11)

# ---------------------------------------------------------------------------
# Generic aliases: use built-ins on 3.9+, typing equivalents on 3.7/3.8
# ---------------------------------------------------------------------------

if PY39:
    Dict = dict
    FrozenSet = frozenset
    List = list
    Set = set
    Tuple = tuple
    Type = type
else:
    from typing import Dict, FrozenSet, List, Set, Tuple, Type  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Standard typing — available since 3.5, always imported from typing
# ---------------------------------------------------------------------------

from typing import (  # noqa: E402
    TYPE_CHECKING,
    Any,
    Final,
    Generic,
    Optional,
    TypeVar,
    Union,
    get_type_hints,
)

L = TypeVar("L")
T = TypeVar("T")

# ---------------------------------------------------------------------------
# Literal, Protocol, TypedDict — available since 3.8, else typing_extensions
# ---------------------------------------------------------------------------

try:
    from typing import Literal, Protocol, TypedDict  # 3.8+
except ImportError:
    from typing_extensions import Literal, Protocol, TypedDict  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# ParamSpec (3.10+) and Self (3.11+) — else typing_extensions
# ---------------------------------------------------------------------------

try:
    from typing import ParamSpec  # 3.10+
except ImportError:
    from typing_extensions import ParamSpec  # type: ignore[assignment]

try:
    from typing import Self  # 3.11+
except ImportError:
    from typing_extensions import Self  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# stdlib backports
# ---------------------------------------------------------------------------

try:
    import importlib.metadata as importlib_metadata  # 3.8+
except ImportError:
    import importlib_metadata  # type: ignore[no-redef]

try:
    import tomllib  # 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

try:
    from zoneinfo import ZoneInfo  # 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "Any",
    "Dict",
    "Final",
    "FrozenSet",
    "Generic",
    "get_type_hints",
    "importlib_metadata",
    "Iterable",
    "L",
    "List",
    "Literal",
    "Mapping",
    "Optional",
    "ParamSpec",
    "Protocol",
    "PY37",
    "PY38",
    "PY39",
    "PY310",
    "PY311",
    "Self",
    "Set",
    "T",
    "tomllib",
    "Tuple",
    "TYPE_CHECKING",
    "Type",
    "TypedDict",
    "TypeVar",
    "Union",
    "ZoneInfo",
]
