# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: manifest.py — oops/rules/manifest.py

"""Fixit lint rules for Odoo ``__manifest__.py`` files.

Rules are auto-discovered by fixit when the module is referenced as a
``QualifiedRule`` (see ``commands/manifest/common.py``). Every public class
that inherits from ``LintRule`` in this module becomes an active rule.

-------------------------------------------------------------------------------
HOW TO ADD A RULE
-------------------------------------------------------------------------------

1. Subclass ``LintRule`` and give it a descriptive name::

       class MyNewRule(LintRule):
           MESSAGE = "Short default message shown when no message= is given."

2. Declare ``AUTOFIX = True`` only if your rule can *always* provide a
   ``replacement`` node. Fixit will warn if you set it but don't supply one.

3. Add ``VALID`` / ``INVALID`` lists of code snippets — fixit runs them as
   inline unit tests (``uv run python -m pytest`` picks them up automatically
   via the fixit pytest plugin).

4. Declare class-level config attributes with safe defaults so the rule works
   even without an ``.oops.yaml`` file. Override them in ``__init__`` from
   ``_load_manifest_cfg()``::

       some_setting: str = ""        # "" → check disabled when no config
       some_list: List[str] = []     # empty → permissive fallback

5. Implement ``visit_<NodeType>(self, node)`` where ``<NodeType>`` matches a
   libcst node class (e.g. ``Dict``, ``SimpleString``, ``Call``). The visitor
   is called for *every* matching node in the file, so use ``self._checked``
   to process only the first top-level dict (the manifest dict itself)::

       def visit_Dict(self, node: cst.Dict) -> None:
           if self._checked:      # ignore nested dicts (depends, data, …)
               return
           self._checked = True
           ...

6. Call ``self.report(node, message="…")`` to flag a violation.
   For autofixes, pass ``replacement=node.with_changes(…)``::

       fixed = node.with_changes(value=cst.SimpleString('"corrected"'))
       self.report(node, message="Wrong value.", replacement=fixed)

7. That's it — no registration needed. The rule is picked up automatically
   because ``common.py`` uses ``QualifiedRule("oops.rules.manifest")``.

-------------------------------------------------------------------------------
LIBCST QUICK REFERENCE
-------------------------------------------------------------------------------

Manifest dicts are Python dict literals, so the relevant CST nodes are:

  cst.Dict          — the ``{ … }`` literal itself
  cst.DictElement   — one ``key: value`` pair inside it
  cst.SimpleString  — a plain string like ``"Acme"`` or ``'16.0.1.0.0'``
  cst.List          — a list literal like ``["alice", "bob"]``
  cst.Element       — one item inside a cst.List

Reading a string value safely:
  ``_string_value(node)``  → returns the Python str or None

Building a replacement node:
  ``node.with_changes(field=new_value)``  — returns a new immutable node

-------------------------------------------------------------------------------
AUTOFIX CONFLICT NOTE
-------------------------------------------------------------------------------

When two rules both provide a ``replacement`` on *overlapping* nodes (e.g.
``ManifestKeyOrder`` replaces the whole dict while ``OdooManifestAuthorMaintainers``
replaces a child string), fixit can only apply one per pass. The outermost
node wins (``ManifestKeyOrder``). The inner fix is applied cleanly on the next
``oops-man-fix`` pass. This is expected and acceptable behaviour.
"""

import re
from typing import Any, List, Optional, Tuple  # noqa: UP035

import libcst as cst
import libcst.matchers as m
from fixit import LintRule
from oops.core.config import ManifestConfig
from oops.rules._helpers import (
    VERSION_PATTERN,
)
from oops.rules._helpers import (
    Elements as _Elements,
)
from oops.rules._helpers import (
    extract_kv as _extract_kv,
)
from oops.rules._helpers import (
    file_at_ref as _file_at_ref,
)
from oops.rules._helpers import (
    get_lint_path as _get_lint_path,
)
from oops.rules._helpers import (
    git_repo_root as _git_repo_root,
)
from oops.rules._helpers import (
    key_name as _key_name,
)
from oops.rules._helpers import (
    last_tag as _last_tag,
)
from oops.rules._helpers import (
    load_manifest_cfg as _load_manifest_cfg,
)
from oops.rules._helpers import (
    module_version as _module_version,
)
from oops.rules._helpers import (
    parse_version_str as _parse_version_str,
)
from oops.rules._helpers import (
    sort_key as _sort_key,
)
from oops.rules._helpers import (
    staged_addon_manifest_relpaths as _staged_addon_manifest_relpaths,
)
from oops.rules._helpers import (
    string_value as _string_value,
)

# ---------------------------------------------------------------------------
# Rule: ManifestRequiredKeys
# ---------------------------------------------------------------------------


class ManifestRequiredKeys(LintRule):
    """Ensure all required keys are present in the manifest dict.

    The list of required keys is read from ``manifest.required_keys`` in
    ``.oops.yaml``; the class-level default covers standalone usage.
    """

    MESSAGE = "Manifest is missing required key(s)."

    # -- Inline fixit tests (run by pytest via the fixit plugin) -------------

    VALID = [
        """{
            "name": "My Addon",
            "version": "16.0.1.0.0",
            "summary": "Does something useful",
            "website": "https://example.com",
            "author": "Acme",
            "maintainers": ["alice"],
            "depends": [],
            "data": [],
            "license": "LGPL-3",
            "auto_install": False,
            "installable": True,
        }"""
    ]

    INVALID = [
        """{
            "name": "My Addon",
            "author": "Acme",
        }""",
    ]

    # -- Config (overridden from .oops.yaml in __init__) ---------------------

    required_keys: List[str] = ManifestConfig().required_keys

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checked = False  # guard: only inspect the first dict in the file
        cfg = _load_manifest_cfg()
        if cfg is not None:
            self.required_keys = cfg.required_keys

    # -- Visitor -------------------------------------------------------------

    def visit_Dict(self, node: cst.Dict) -> None:
        # _checked prevents re-running on nested dicts (e.g. inside "data": {…})
        if self._checked:
            return
        self._checked = True

        kv = _extract_kv(node)
        for key in self.required_keys:
            if key not in kv:
                self.report(node, message=f"Manifest is missing required key '{key}'.")


# ---------------------------------------------------------------------------
# Rule: OdooManifestAuthorMaintainers
# ---------------------------------------------------------------------------


class OdooManifestAuthorMaintainers(LintRule):
    """Validate manifest field values: author, maintainers, summary, version.

    All four checks run in a single ``visit_Dict`` pass; each is extracted into
    its own ``_check_*`` method so they can be read and extended independently.

    Autofixable checks
    ~~~~~~~~~~~~~~~~~~
    - ``author``  — replaced with the configured value (preserves quote style)
    - ``version`` — digit-lookalike typos corrected (O→0, l/I→1) when the
                    corrected string passes the pattern
    """

    AUTOFIX = True
    MESSAGE = "Invalid Odoo manifest metadata."

    # -- Config (overridden from .oops.yaml in __init__) ---------------------

    expected_author: str = ""  # "" → check disabled when no config is loaded
    odoo_version: Optional[str] = None  # e.g. "19.0"; None → generic 5-part pattern
    allowed_maintainers: List[str] = ManifestConfig().allowed_maintainers

    # -- Inline fixit tests --------------------------------------------------

    VALID = [
        """{
            "name": "My Addon",
            "summary": "Manage business data.",
            "author": "Acme",
            "maintainers": ["alice"],
            "license": "LGPL-3",
        }"""
    ]

    INVALID = [
        # wrong author
        """{
            "name": "My Addon",
            "summary": "Manage business data.",
            "author": "SomeoneElse",
            "maintainers": ["alice"],
            "license": "LGPL-3",
        }""",
        # unknown maintainer
        """{
            "name": "My Addon",
            "summary": "Manage business data.",
            "author": "Acme",
            "maintainers": ["unknown_user"],
            "license": "LGPL-3",
        }""",
        # empty summary
        """{
            "name": "My Addon",
            "summary": "",
            "author": "Acme",
            "maintainers": ["alice"],
            "license": "LGPL-3",
        }""",
        # summary == name
        """{
            "name": "My Addon",
            "summary": "My Addon",
            "author": "Acme",
            "maintainers": ["alice"],
            "license": "LGPL-3",
        }""",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checked = False
        cfg = _load_manifest_cfg()
        if cfg is not None:
            self.expected_author = cfg.author
            self.odoo_version = cfg.odoo_version
            self.allowed_maintainers = cfg.allowed_maintainers

    # -- Visitor -------------------------------------------------------------

    def visit_Dict(self, node: cst.Dict) -> None:
        if self._checked:
            return
        self._checked = True

        kv = _extract_kv(node)
        self._check_author(kv)
        self._check_maintainers(kv)
        self._check_summary(kv)
        self._check_version(kv)

    # -- Per-field checks ----------------------------------------------------

    def _check_author(self, kv: "dict[str, cst.BaseExpression]") -> None:
        """Report (and autofix) when 'author' doesn't match expected_author.

        Skipped entirely when expected_author is empty (no config loaded).
        The replacement preserves the original quote character (' or ").
        """
        if not self.expected_author:
            return

        author_node = kv.get("author")
        if author_node is None:
            return

        val = _string_value(author_node)
        if val == self.expected_author:
            return

        replacement = None
        if isinstance(author_node, cst.SimpleString):
            q = author_node.value[0]  # preserve original quote style (' or ")
            replacement = author_node.with_changes(value=f"{q}{self.expected_author}{q}")

        self.report(
            author_node,
            message=f"Manifest 'author' must be exactly {self.expected_author!r}, got {val!r}.",
            replacement=replacement,
        )

    def _check_maintainers(self, kv: "dict[str, cst.BaseExpression]") -> None:
        """Report when 'maintainers' is not a non-empty list of allowed handles."""
        maintainers_node = kv.get("maintainers")
        if maintainers_node is None:
            return

        # Must be a list literal, not a variable reference or other expression.
        if not m.matches(maintainers_node, m.List()):
            self.report(maintainers_node, message="'maintainers' must be a list.")
            return

        assert isinstance(maintainers_node, cst.List)
        handles = [el.value for el in maintainers_node.elements if isinstance(el, cst.Element)]

        if not handles:
            self.report(maintainers_node, message="'maintainers' must not be empty.")
            return

        allowed_set = set(self.allowed_maintainers)
        for handle_node in handles:
            handle = _string_value(handle_node)
            if handle is None:
                self.report(handle_node, message="Each maintainer entry must be a plain string.")
            elif allowed_set and handle not in allowed_set:
                # Skip the allowed-list check when the list is empty (no config).
                self.report(
                    handle_node,
                    message=(f"Maintainer {handle!r} is not in the allowed list: {sorted(allowed_set)}."),
                )

    def _check_summary(self, kv: "dict[str, cst.BaseExpression]") -> None:
        """Report when 'summary' is empty or identical to 'name'."""
        summary_node = kv.get("summary")
        if summary_node is None:
            return

        summary_val = _string_value(summary_node)
        if summary_val is None:
            return

        if not summary_val.strip():
            self.report(summary_node, message="'summary' must not be empty.")
            return

        name_node = kv.get("name")
        if name_node is not None:
            name_val = _string_value(name_node)
            if name_val is not None and summary_val.strip() == name_val.strip():
                self.report(summary_node, message="'summary' must differ from 'name'.")

    def _check_version(self, kv: "dict[str, cst.BaseExpression]") -> None:
        """Report when 'version' doesn't match the expected Odoo version pattern.

        Pattern when ``odoo_version`` is set (e.g. "19.0"):
            ``^19\\.0\\.\\d+\\.\\d+\\.\\d+$``  → "19.0.1.0.0"

        Pattern when ``odoo_version`` is not set (generic):
            ``^\\d+\\.\\d+\\.\\d+\\.\\d+\\.\\d+$``  → "16.0.1.0.0"

        Autofix: digit-lookalike typos are corrected automatically when the
        corrected string passes the pattern (O→0, l→1, I→1).
        """
        version_node = kv.get("version")
        if version_node is None:
            return

        val = _string_value(version_node)
        if val is None:
            return

        if self.odoo_version:
            prefix = re.escape(self.odoo_version)
            pattern = rf"^{prefix}\.\d+\.\d+\.\d+$"
            odoo_label = self.odoo_version
            example = f"{self.odoo_version}.1.0.0"
        else:
            pattern = VERSION_PATTERN
            odoo_label = "<odoo_version>"
            example = "16.0.1.0.0"

        if re.match(pattern, val):
            return

        # Attempt autofix for common digit-lookalike typos before reporting.
        corrected = val.translate(str.maketrans("OlI", "011"))
        replacement = None
        if re.match(pattern, corrected) and isinstance(version_node, cst.SimpleString):
            q = version_node.value[0]
            replacement = version_node.with_changes(value=f"{q}{corrected}{q}")

        self.report(
            version_node,
            message=(
                f"Manifest 'version' must follow {odoo_label}.<x>.<y>.<z> format (e.g. {example!r}), got {val!r}."
            ),
            replacement=replacement,
        )


# ---------------------------------------------------------------------------
# Rule: ManifestNoExtraKeys
# ---------------------------------------------------------------------------


class ManifestNoExtraKeys(LintRule):
    """Reject keys not present in the configured allowed list.

    Unknown keys are likely typos or leftover debug entries. The allowed list
    is the same as ``key_order`` from ``.oops.yaml`` so both rules stay in sync.
    """

    MESSAGE = "Manifest contains unknown key(s)."

    VALID = [
        """{
            "name": "My Addon",
            "version": "16.0.1.0.0",
            "summary": "Does something.",
            "author": "Acme",
            "installable": True,
        }"""
    ]

    INVALID = [
        """{
            "name": "My Addon",
            "debug_flag": True,
        }""",
    ]

    allowed_keys: List[str] = ManifestConfig().key_order

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checked = False
        cfg = _load_manifest_cfg()
        if cfg is not None:
            self.allowed_keys = cfg.key_order

    def visit_Dict(self, node: cst.Dict) -> None:
        if self._checked:
            return
        self._checked = True

        allowed = set(self.allowed_keys)
        for el in node.elements or []:
            if not isinstance(el, cst.DictElement):
                continue
            if isinstance(el.key, cst.SimpleString):
                key = el.key.value.strip("'\"")
                if key not in allowed:
                    self.report(
                        el.key,
                        message=f"Unknown manifest key {key!r}. Allowed: {sorted(allowed)}.",
                    )


# ---------------------------------------------------------------------------
# Rule: ManifestKeyOrder
# ---------------------------------------------------------------------------


class ManifestKeyOrder(LintRule):
    """Enforce the canonical key order in ``__manifest__.py`` dict literals.

    The replacement node preserves all comments and trailing commas; only the
    element sequence is reordered. Keys absent from ``key_order`` are sorted
    after all known keys (stable, alphabetical).

    Because this rule replaces the *whole dict node*, its autofix takes
    priority over child-node fixes from other rules in the same fixit pass.
    Run ``oops-man-fix`` a second time to apply those remaining fixes.
    """

    AUTOFIX = True
    key_order: List[str] = ManifestConfig().key_order

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cfg = _load_manifest_cfg()
        if cfg is not None:
            self.key_order = cfg.key_order

    # -- Visitor -------------------------------------------------------------

    def visit_Dict(self, node: cst.Dict) -> None:
        if not node.elements:
            return

        elements = self._cast_elements(node)
        if self._elements_in_order(elements):
            return

        current = [_key_name(e) for e in elements if isinstance(e, cst.DictElement)]
        expected = [_key_name(e) for e in self._sorted_elements(elements) if isinstance(e, cst.DictElement)]
        self.report(
            node,
            message=(f"Manifest keys are not in the expected order.\n  Current : {current}\n  Expected: {expected}"),
            replacement=node.with_changes(elements=self._rebuild_elements(self._sorted_elements(elements))),
        )

    # -- Helpers -------------------------------------------------------------

    def _cast_elements(self, node: cst.Dict) -> _Elements:
        return node.elements  # type: ignore[return-value]

    def _sorted_elements(self, elements: _Elements) -> List[Any]:
        order = self.key_order

        def sort_fn(el: Any) -> Tuple[int, str]:
            # StarredDictElement (**kwargs) always goes last.
            if isinstance(el, cst.StarredDictElement):
                return (len(order) + 1, "")
            return _sort_key(_key_name(el), order)

        return sorted(elements, key=sort_fn)

    def _elements_in_order(self, elements: _Elements) -> bool:
        """Return True when elements already match the expected order."""
        sorted_els = self._sorted_elements(elements)
        current = [_key_name(e) for e in elements if isinstance(e, cst.DictElement)]
        expected = [_key_name(e) for e in sorted_els if isinstance(e, cst.DictElement)]
        return current == expected

    def _rebuild_elements(self, sorted_els: List[Any]) -> List[Any]:
        """Re-assign commas so the last element has no trailing comma issue.

        libcst stores each comma on the *preceding* element, so after reordering
        we must ensure the new last element doesn't carry a comma, and every
        other element does.
        """
        result = []
        last_idx = len(sorted_els) - 1
        for i, el in enumerate(sorted_els):
            if isinstance(el, cst.DictElement):
                if i == last_idx:
                    # MaybeSentinel.DEFAULT lets libcst decide (usually no comma).
                    comma: Any = cst.MaybeSentinel.DEFAULT
                elif isinstance(el.comma, cst.Comma):
                    comma = el.comma  # keep original comma (preserves whitespace)
                else:
                    comma = cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                el = el.with_changes(comma=comma)  # noqa: PLW2901
            result.append(el)
        return result


# ---------------------------------------------------------------------------
# Rule: ManifestVersionBump
# ---------------------------------------------------------------------------


class ManifestVersionBump(LintRule):
    """Verify that the manifest version is bumped when addon files are staged.

    This rule is git-aware: it reads the list of staged files from the index,
    determines which addons are affected, and only activates for those. Addons
    that have no staged files are silently skipped, so the rule is safe to
    run on all manifests via ``oops-man-check``.

    Two strategies are supported (set ``manifest.version_bump_strategy`` in
    ``.oops.yaml``):

    ``strict`` (default when not ``off``)
        The staged version must be strictly greater than the version at HEAD.
        Enforces a version bump on every commit that touches the addon.

    ``trunk``
        The staged version must be strictly greater than the version at the
        last git tag. One bump per release cycle is sufficient — fits
        trunk-based / squash-merge workflows.

    ``off`` (default)
        Rule is disabled. Set explicitly to activate::

            manifest:
              version_bump_strategy: strict   # or trunk

    New addons (absent from the reference commit / tag) are always exempt.
    Only the module-specific tail of the version is compared (last 3 parts
    of the 5-part Odoo string), so migrating to a new Odoo major version
    without bumping the module version does not trigger a false positive.
    """

    MESSAGE = "Manifest version must be bumped."

    # Class-level default — overridden from config in __init__.
    version_bump_strategy: str = "off"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checked = False
        self._ref_version: Optional[Tuple[int, ...]] = None

        # Load strategy from config (falls back to class default "off").
        cfg = _load_manifest_cfg()
        strategy = cfg.version_bump_strategy if cfg is not None else self.version_bump_strategy

        if strategy == "off":
            return  # rule disabled

        # Determine the git reference to compare against.
        if strategy == "trunk":
            ref: Optional[str] = _last_tag()
            if ref is None:
                return  # no tag yet, nothing to compare against
        else:
            ref = "HEAD"

        # Identify which file we're currently linting.
        # set_lint_path() is called by run_fixit() before fixit_file() per path.
        path = _get_lint_path()
        if path is None:
            return

        repo_root = _git_repo_root()
        if repo_root is None:
            return

        try:
            rel_path = str(path.relative_to(repo_root))
        except ValueError:
            return

        # Only activate for manifests whose addon has staged changes.
        if rel_path not in _staged_addon_manifest_relpaths():
            return

        # Fetch the reference manifest and extract its version.
        ref_src = _file_at_ref(rel_path, ref)
        if ref_src is None:
            return  # new addon at this ref → exempt

        self._ref_version = _parse_version_str(ref_src)

    # -- Visitor -------------------------------------------------------------

    def visit_Dict(self, node: cst.Dict) -> None:
        # _ref_version is None when the rule is inactive (strategy="off",
        # addon not staged, new addon, or no config).
        if self._checked or self._ref_version is None:
            return
        self._checked = True

        kv = _extract_kv(node)
        version_node = kv.get("version")
        if version_node is None:
            return

        val = _string_value(version_node)
        if val is None:
            return

        try:
            staged_ver: Tuple[int, ...] = tuple(int(p) for p in val.split("."))
        except ValueError:
            return  # unparseable — caught by OdooManifestAuthorMaintainers

        if _module_version(staged_ver) <= _module_version(self._ref_version):
            ref_str = ".".join(map(str, self._ref_version))
            self.report(
                version_node,
                message=(
                    f"Version not bumped: {val!r} must be greater than "
                    f"{ref_str!r} (strategy: {self.version_bump_strategy!r})"
                ),
            )
