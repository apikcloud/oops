# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: compat.py — oops/utils/compat.py

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Dict, Final, Generic, List, Optional, Tuple, Type, TypeVar, Union, get_type_hints

PY37 = sys.version_info < (3, 8)
PY38 = sys.version_info < (3, 9)
PY39 = sys.version_info < (3, 10)
PY311 = sys.version_info >= (3, 11)

# typing
try:
    from typing import Literal, Protocol, TypedDict
except ImportError:  # 3.7–3.10
    from typing_extensions import (  # type: ignore
        Literal,
        ParamSpec,
        Protocol,
        Self,
        TypedDict,
    )


# stdlib backports
try:
    import importlib.metadata as importlib_metadata  # py39+
except Exception:
    import importlib_metadata  # type: ignore

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore

try:
    from zoneinfo import ZoneInfo  # py39+
except Exception:
    from backports.zoneinfo import ZoneInfo  # type: ignore

L = TypeVar("L")
T = TypeVar("T")

__all__ = [
    "Any",
    "Dict",
    "Final",
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
    "Self",
    "T",
    "tomllib",
    "Tuple",
    "TYPE_CHECKING",
    "Type",
    "TypedDict",
    "Union",
    "ZoneInfo",
]
