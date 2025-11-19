import libcst as cst
import libcst.matchers as m
from fixit import LintRule


class HollywoodName(LintRule):
    VALID = [...]  # no lint errors here
    INVALID = [...]  # bad code samples here

    def visit_SimpleString(self, node: cst.SimpleString):
        if node.value in ('"Paul"', "'Paul'"):
            self.report(node, "It's underbaked!")


class UseRequestTimeouts(LintRule):
    MESSAGE = "HTTP calls must specify a timeout"

    def visit_Call(self, node: cst.Call) -> None:
        is_http_call = m.matches(node.func, m.Name("get"))
        has_timeout_argument = m.matches(
            node,
            m.Call(
                func=m.DoNotCare(),
                args=[
                    m.ZeroOrMore(),
                    m.Arg(
                        keyword=m.Name("timeout"),
                        value=m.DoNotCare(),
                    ),
                    m.ZeroOrMore(),
                ],
            ),
        )
        if is_http_call and not has_timeout_argument:
            self.report(node)
