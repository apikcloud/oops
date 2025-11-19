import libcst as cst
import libcst.matchers as m

from oops.compat import Any, Optional


def _decode_string(node: cst.SimpleString) -> str:
    """Minimal unquoting for '...', "...", '''...''', \"\"\"...\"\"\"."""
    raw = node.value  # includes quotes
    q3 = raw[:3] in ("'''", '"""')
    q = 3 if q3 else 1
    s = raw[q:-q]
    return bytes(s, "utf-8").decode("unicode_escape")


def _decode_value(node: cst.CSTNode) -> Any:
    """Decode common manifest literals using matchers only for CST types."""
    # strings
    if m.matches(node, m.SimpleString()):
        s = m.extract(node, m.SimpleString())
        return _decode_string(s)


class TypingCollector(cst.CSTVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.manifest: dict[str, Any] = {}
        self._top_dict: Optional[cst.Dict] = None
        self._dict_stack: list[cst.Dict] = []

    # --- discover the top-level dict in Module ---

    def visit_Module(self, node: cst.Module) -> None:
        if not node.body or not m.matches(node.body[0], m.SimpleStatementLine()):
            self.errors.append("Expected a single top-level simple statement.")
            return

        # ssl = m.extract(node.body, m.SimpleStatementLine())
        # expr = m.extract(ssl, m.Expr())
        # print(expr)
        # top = expr.value

        # if m.matches(top, m.Dict()):
        #     self._top_dict = m.extract(top, m.Dict())
        #     return

    # --- track dict nesting so we know when we're in the manifest root ---

    def visit_Dict(self, node: cst.Dict) -> None:
        print("j'entre dans un dict")
        self._dict_stack.append(node)

    def leave_Dict(self, node: cst.Dict) -> None:
        print("je sors du dict")
        self._dict_stack.pop()

    # --- collect first-level key/values (only when inside _top_dict) ---

    def visit_DictElement(self, node: cst.DictElement) -> None:
        if not self._dict_stack:
            return
        # Only capture elements belonging to the root manifest dict
        # if self._dict_stack[-1] is not self._top_dict:
        #     return

        print("bip")

        # print(node.key)

        if m.matches(node, m.SimpleString()):
            s = m.extract(node.value, m.SimpleString())
            print(s)
        else:
            print("pas de simple string ici")

        # key_py = _decode_value(node.key)
        # key_str = key_py if isinstance(key_py, str) else str(key_py)  # plain Python, not CST
        # self.manifest[key_str] = _decode_value(node.value)

    def visit_SimpleString(self, node):
        print(f"coucou: {node.value}")
