# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops upgrade vanilla — discovery, ordering, script generation, git mutation, CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner
from git import Repo
from oops.commands.upgrade.vanilla import (
    UNINSTALL_SCRIPT_TEMPLATE,
    VanillaModule,
    compute_removal_order,
    discover_non_core_addons,
    flag_kb_collisions,
    main,
    render_uninstall_script,
)
from oops.core.exceptions import OopsError


def _make_addon_dir(base: Path, name: str, author: str = "Acme", depends=None, website=None):
    d = base / name
    d.mkdir(parents=True)
    manifest = {"name": name, "author": author, "depends": depends or []}
    if website:
        manifest["website"] = website
    (d / "__manifest__.py").write_text(repr(manifest))
    return d


# ---------------------------------------------------------------------------
# discover_non_core_addons
# ---------------------------------------------------------------------------


def test_discover_non_core_addons_classifies(tmp_path):
    _make_addon_dir(tmp_path, "custom_sale", author="Acme")
    _make_addon_dir(
        tmp_path, "oca_partner", author="Odoo Community Association (OCA)", website="https://github.com/OCA/partner-contact"
    )
    _make_addon_dir(tmp_path, "third_party_mod", author="Some Vendor")

    addons = discover_non_core_addons(tmp_path, {})
    by_name = {a.technical_name: a for a in addons}

    assert set(by_name) == {"custom_sale", "oca_partner", "third_party_mod"}
    assert by_name["custom_sale"].classification == "custom"
    assert by_name["oca_partner"].classification == "oca"
    assert by_name["third_party_mod"].classification == "third-party"
    assert all(a.location == "local" for a in addons)


# ---------------------------------------------------------------------------
# compute_removal_order
# ---------------------------------------------------------------------------


def _vm(name, depends=()):
    from unittest.mock import MagicMock

    a = MagicMock()
    a.technical_name = name
    a.depends = list(depends)
    a.classification = "custom"
    a.location = "local"
    a.submodule = ""
    return a


def test_compute_removal_order_linear_chain():
    # A depends on B, B depends on C — safe uninstall order: A, B, C.
    a = _vm("a", depends=["b"])
    b = _vm("b", depends=["c"])
    c = _vm("c", depends=[])
    modules = compute_removal_order([a, b, c])
    assert [m.name for m in modules] == ["a", "b", "c"]


def test_compute_removal_order_independent_chains_preserve_internal_order():
    # Two independent chains: a1->a2 and b1->b2. Exact interleaving between
    # chains is not asserted (compute_load_order's tie-break is alphabetical),
    # only that each chain's internal order survives.
    a1 = _vm("a1", depends=["a2"])
    a2 = _vm("a2", depends=[])
    b1 = _vm("b1", depends=["b2"])
    b2 = _vm("b2", depends=[])
    modules = compute_removal_order([a1, a2, b1, b2])
    order = [m.name for m in modules]
    assert order.index("a1") < order.index("a2")
    assert order.index("b1") < order.index("b2")


def test_compute_removal_order_cycle_raises():
    a = _vm("a", depends=["b"])
    b = _vm("b", depends=["a"])
    with pytest.raises(OopsError):
        compute_removal_order([a, b])


# ---------------------------------------------------------------------------
# flag_kb_collisions
# ---------------------------------------------------------------------------


def test_flag_kb_collisions_detects_match():
    modules = [
        VanillaModule(name="sale", classification="custom", location="local", load_index=0),
        VanillaModule(name="my_custom_mod", classification="custom", location="local", load_index=1),
    ]
    fake_kb = {"sale": {"origin": "odoo", "depends": []}}
    with patch("oops.commands.upgrade.vanilla.load_odoo_kb", return_value=fake_kb):
        kb_checked, warnings = flag_kb_collisions(modules, "18.0")

    assert kb_checked is True
    sale = next(m for m in modules if m.name == "sale")
    other = next(m for m in modules if m.name == "my_custom_mod")
    assert sale.matched_origin == "core"
    assert other.matched_origin is None
    assert len(warnings) == 1
    assert "sale" in warnings[0]


def test_flag_kb_collisions_no_kb_built():
    modules = [VanillaModule(name="my_custom_mod", classification="custom", location="local", load_index=0)]
    with patch("oops.commands.upgrade.vanilla.load_odoo_kb", return_value={}):
        kb_checked, warnings = flag_kb_collisions(modules, "18.0")

    assert kb_checked is False
    assert len(warnings) == 1
    assert modules[0].matched_origin is None


# ---------------------------------------------------------------------------
# render_uninstall_script
# ---------------------------------------------------------------------------


def test_render_uninstall_script_contents():
    modules = [
        VanillaModule(name="a", classification="custom", location="local", load_index=2),
        VanillaModule(name="b", classification="custom", location="local", load_index=1),
    ]
    content = render_uninstall_script(modules)
    assert "from odoo.upgrade import util" in content
    assert '("a", 2),' in content
    assert '("b", 1),' in content
    assert "util.module_installed(cr, module)" in content
    assert content.index('("a", 2),') < content.index('("b", 1),')


def test_render_uninstall_script_uses_shared_template():
    assert render_uninstall_script([]).count("MODULES = [") == UNINSTALL_SCRIPT_TEMPLATE.count("MODULES = [")


# ---------------------------------------------------------------------------
# CLI integration (real git repos — `main` performs real branch/commit/tag
# operations, so these are not mocked like the analyze/plan CLI tests).
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> Repo:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)
    with repo.config_writer() as cw:
        cw.set_value("user", "email", "test@test.com")
        cw.set_value("user", "name", "Test")
    (repo_path / "odoo_version.txt").write_text("apik/odoo:18.0-20240101\n")
    repo.index.add([str(repo_path / "odoo_version.txt")])
    repo.index.commit("init")
    return repo


def _add_local_addon(repo_path: Path, name: str, author: str = "Acme", depends=None) -> Path:
    d = repo_path / name
    d.mkdir(parents=True)
    manifest = {"name": name, "author": author, "depends": depends or []}
    (d / "__manifest__.py").write_text(repr(manifest))
    return d


def _commit_all(repo: Repo, message: str) -> None:
    repo.git.add("-A")
    repo.index.commit(message)


def test_cli_force_strips_local_addon(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "custom_mod")
    _commit_all(repo, "add addon")

    monkeypatch.chdir(repo_path)
    result = CliRunner().invoke(main, ["--force"])

    assert result.exit_code == 0, result.output
    assert not (repo_path / "custom_mod").exists()
    script_path = repo_path / "upgrades" / "base" / "0.0.0" / "end-uninstall_non_core_modules.py"
    assert script_path.exists()
    assert '"custom_mod"' in script_path.read_text()
    requirements = (repo_path / "requirements.txt").read_text()
    assert "odoo_upgrade @ git+https://github.com/odoo/upgrade-util@master" in requirements
    assert "git" in (repo_path / "packages.txt").read_text().split()
    assert "vanilla/18.0" in [h.name for h in repo.heads]
    assert "vanilla-18.0" in [t.name for t in repo.tags]
    assert repo.is_dirty() is False


def test_cli_dry_run_leaves_tree_unchanged(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "custom_mod")
    _commit_all(repo, "add addon")

    before = repo.git.status("--porcelain")
    monkeypatch.chdir(repo_path)
    result = CliRunner().invoke(main, ["--dry-run"])

    assert result.exit_code == 0, result.output
    assert (repo_path / "custom_mod").exists()
    assert not (repo_path / "upgrades").exists()
    assert repo.git.status("--porcelain") == before
    assert [h.name for h in repo.heads] == ["master"] or [h.name for h in repo.heads] == ["main"]


def test_cli_no_addons_exits_error(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)

    monkeypatch.chdir(repo_path)
    result = CliRunner().invoke(main, ["--force"])

    assert result.exit_code != 0
    assert "nothing to strip" in result.output.lower() or "no non-core addons" in result.output.lower()


def test_cli_kb_collision_still_removed_with_warning(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "sale_extra")
    _commit_all(repo, "add addon")

    fake_kb = {"sale_extra": {"origin": "odoo", "depends": []}}
    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.load_odoo_kb", return_value=fake_kb):
        result = CliRunner().invoke(main, ["--force", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert not (repo_path / "sale_extra").exists()
    json_start = result.output.index("{")
    payload = json.loads(result.output[json_start:])
    assert payload["kb_checked"] is True
    assert payload["modules"][0]["matched_origin"] == "core"
    assert any("sale_extra" in w for w in payload["warnings"])


def test_cli_packages_txt_merges_existing_entries(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "custom_mod")
    (repo_path / "packages.txt").write_text("postgresql-client\nvim\n")
    _commit_all(repo, "add addon and packages")

    monkeypatch.chdir(repo_path)
    result = CliRunner().invoke(main, ["--force"])

    assert result.exit_code == 0, result.output
    packages = (repo_path / "packages.txt").read_text().split()
    assert set(packages) == {"git", "postgresql-client", "vim"}


def test_cli_submodule_addon_removed_no_dangling_gitmodules(tmp_path, monkeypatch):
    """Regression: submodule matching must not rely on Submodule.name being
    an "owner/repo" slug — a submodule added with plain `git submodule add`
    (no explicit --name) has a path-shaped name, and matching against it by
    string-splitting silently drops the action, leaving "nothing to strip"
    even though a real submodule-backed addon was discovered.
    """
    upstream_path = tmp_path / "upstream"
    upstream_path.mkdir()
    upstream = Repo.init(upstream_path)
    with upstream.config_writer() as cw:
        cw.set_value("user", "email", "test@test.com")
        cw.set_value("user", "name", "Test")
    _add_local_addon(upstream_path, "oca_mod", author="Odoo Community Association (OCA)")
    upstream.index.add(["oca_mod"])
    upstream.index.commit("init upstream")

    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    (repo_path / ".third-party").mkdir()
    with repo.git.custom_environment(GIT_ALLOW_PROTOCOL="file"):
        repo.git.submodule("add", str(upstream_path), ".third-party/oca_mod")
    (repo_path / "oca_mod").symlink_to(repo_path / ".third-party" / "oca_mod" / "oca_mod")
    _commit_all(repo, "add submodule")

    monkeypatch.chdir(repo_path)
    result = CliRunner().invoke(main, ["--force"])

    assert result.exit_code == 0, result.output
    assert "Nothing to strip" not in result.output
    assert not (repo_path / "oca_mod").exists()
    assert not (repo_path / ".third-party" / "oca_mod" / ".git").exists()
    gitmodules = repo_path / ".gitmodules"
    content = gitmodules.read_text() if gitmodules.exists() else ""
    assert "oca_mod" not in content

    report_path = repo_path / ".oops" / "upgrade" / "vanilla.yml"
    report = yaml.safe_load(report_path.read_text())
    assert report["modules"][0]["name"] == "oca_mod"
