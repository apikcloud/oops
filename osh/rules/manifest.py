import libcst as cst
import libcst.matchers as m
from fixit import LintRule


class OdooManifestAuthorMaintainers(LintRule):
    """
    Ensure Odoo manifest dict contains:
      - author == "Apik"
      - maintainers: non-empty list of allowed GitHub handles
    """

    MESSAGE = "Invalid Odoo manifest metadata."
    ALLOWED_HANDLES = {"apikcloud", "aurelien-roy", "apik-dev"}  # <-- extend as needed

    # Optional examples for Fixit docs/tests
    VALID = [
        # Only one top-level dict is expected in __manifest__.py or __openerp__.py
        """{
            "name": "APIK DATA",
            "author": "Apik",
            "maintainers": ["apikcloud", "aurelien-roy"]
        }"""
    ]

    INVALID = [
        """{
            "name": "APIK DATA",
            "author": "SomeoneElse",
            "maintainers": ["randomuser"]
        }""",
        """{
            "name": "APIK DATA",
            "author": "Apik",
            "maintainers": []
        }""",
        """{
            "name": "APIK DATA",
            "author": "Apik"
            # missing maintainers
        }""",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checked_first_dict = False

    def visit_Dict(self, node: cst.Dict) -> None:
        # Heuristic: treat the first dict in the file as the manifest.
        if self._checked_first_dict:
            return
        self._checked_first_dict = True

        # Build a simple map of string keys -> value nodes
        kv = {}
        for el in node.elements or []:
            if el is None or el.key is None:
                continue
            if m.matches(el.key, m.SimpleString()):
                key = el.key.evaluated_value  # unquoted key
                kv[key] = el.value

        # ---- Check "author" ----
        author = kv.get("author")
        if author is None:
            self.report(node, message="Manifest is missing 'author' key.")
        elif not m.matches(
            author, m.SimpleString(value=m.MatchIfTrue(lambda s: s in ('"Apik"', "'Apik'")))
        ):
            self.report(author, message="Manifest 'author' must be exactly 'Apik'.")

        # ---- Check "maintainers" ----
        maintainers = kv.get("maintainers")
        if maintainers is None:
            self.report(node, message="Manifest is missing 'maintainers' key.")
            return

        if not m.matches(maintainers, m.List()):
            self.report(maintainers, message="'maintainers' must be a list.")
            return
