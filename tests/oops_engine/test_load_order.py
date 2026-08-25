# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from oops_engine.load_order import compute_load_order


class TestComputeLoadOrder:
    def test_linear_chain(self):
        installed = {"base", "sale", "sale_management", "custom_sale"}
        depends = {
            "base": [],
            "sale": ["base"],
            "sale_management": ["sale"],
            "custom_sale": ["sale_management"],
        }
        result = compute_load_order(installed, depends)
        assert result["base"] == (0, 0)
        assert result["sale"] == (1, 1)
        assert result["sale_management"] == (2, 2)
        assert result["custom_sale"] == (3, 3)

    def test_tie_break_alphabetical(self):
        installed = {"base", "alpha", "beta"}
        depends = {
            "base": [],
            "alpha": ["base"],
            "beta": ["base"],
        }
        result = compute_load_order(installed, depends)
        assert result["base"][0] == 0
        assert result["alpha"][0] == result["beta"][0] == 1
        # alphabetical tie-break: alpha before beta
        assert result["alpha"][1] < result["beta"][1]

    def test_dropped_deps(self):
        # dep not in installed silently dropped; module acts as root
        installed = {"mail", "sale"}
        depends = {
            "mail": ["base"],   # base not installed
            "sale": ["mail"],
        }
        result = compute_load_order(installed, depends)
        assert result["mail"][0] == 0
        assert result["sale"][0] == 1

    def test_empty_installed(self):
        result = compute_load_order(set(), {})
        assert result == {}

    def test_single_module(self):
        result = compute_load_order({"base"}, {"base": []})
        assert result == {"base": (0, 0)}

    def test_diamond(self):
        # base → a, base → b, a+b → c
        installed = {"base", "a", "b", "c"}
        depends = {
            "base": [],
            "a": ["base"],
            "b": ["base"],
            "c": ["a", "b"],
        }
        result = compute_load_order(installed, depends)
        assert result["base"][0] == 0
        assert result["a"][0] == 1
        assert result["b"][0] == 1
        assert result["c"][0] == 2
        # load_index of c must be after both a and b
        assert result["c"][1] > result["a"][1]
        assert result["c"][1] > result["b"][1]
