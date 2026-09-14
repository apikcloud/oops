# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for oops upgrade vanilla — discovery, ordering, script generation, git mutation, CLI."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner
from git import Repo
from oops.commands.upgrade.vanilla import (
    UNINSTALL_SCRIPT_TEMPLATE,
    VanillaModule,
    build_strip_plan,
    bump_odoo_version,
    cleanup_submodule_containers,
    compute_removal_order,
    discover_non_core_addons,
    flag_kb_collisions,
    load_installed_context,
    main,
    render_uninstall_script,
    sync_project_files,
)
from oops.core.exceptions import OopsError
from oops.core.models import ImageInfo


def _fake_find_available_images(version, enterprise, release=None, target_date=None):
    """Stand-in for `services.docker.find_available_images` — no network."""
    return [
        ImageInfo(
            image=f"apik/odoo:{version}-20260101",
            registry="apik",
            repository="odoo",
            major_version=version,
            release=date(2026, 1, 1),
            enterprise=enterprise,
        )
    ]


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


def test_compute_removal_order_single_addon_is_trivially_zero_without_extra_depends():
    """Regression baseline for the exact reported symptom: with a single
    discovered addon depending only on (undiscovered) core modules, it's the
    only entry in `installed` — load_index is trivially 0, regardless of how
    deep its real dependency chain actually is in the Odoo registry.
    """
    a = _vm("addon_a", depends=["sale"])
    modules = compute_removal_order([a])
    assert modules[0].load_index == 0


def test_compute_removal_order_with_extra_depends_reflects_real_depth():
    """With the real core dependency chain supplied (as load_installed_context
    would from installed_modules.txt + the KB), the same single addon's
    load_index reflects its actual position past its real dependencies —
    no longer trivially 0 — and two addons resolving through chains of
    different depth are differentiated and correctly ordered.
    """
    a = _vm("addon_a", depends=["sale"])  # base -> sale -> addon_a
    extra_depends = {"base": [], "sale": ["base"]}
    modules = compute_removal_order([a], extra_depends)
    assert modules[0].load_index > 0

    b = _vm("addon_b", depends=["crm"])  # base -> sale -> crm -> addon_b
    extra_depends = {"base": [], "sale": ["base"], "crm": ["sale"]}
    modules = compute_removal_order([a, b], extra_depends)
    by_name = {m.name: m.load_index for m in modules}
    assert by_name["addon_b"] > by_name["addon_a"]
    # addon_b (deeper chain) must be removed before addon_a.
    assert [m.name for m in modules].index("addon_b") < [m.name for m in modules].index("addon_a")


# ---------------------------------------------------------------------------
# load_installed_context
# ---------------------------------------------------------------------------


def test_load_installed_context_missing_file_warns(tmp_path):
    a = _vm("addon_a", depends=["sale"])
    extra_depends, warnings = load_installed_context(tmp_path, [a], "14.0")
    assert extra_depends == {}
    assert len(warnings) == 1
    assert "installed_modules.txt" in warnings[0]
    assert "not found" in warnings[0]


def test_load_installed_context_resolves_from_kb(tmp_path):
    _make_addon_dir(tmp_path, "addon_a", depends=["sale"])
    (tmp_path / "installed_modules.txt").write_text("addon_a\nsale\nbase\n")

    fake_kb = {
        "sale": {"origin": "odoo", "depends": ["base"]},
        "base": {"origin": "odoo", "depends": []},
    }
    a = _vm("addon_a", depends=["sale"])
    with patch("oops.commands.upgrade.vanilla.load_odoo_kb", return_value=fake_kb):
        extra_depends, warnings = load_installed_context(tmp_path, [a], "14.0")

    assert extra_depends == {"sale": ["base"], "base": []}
    # sale/base are core (no addon at root) — expected, not an error.
    assert any("no addon at the repo root" in w for w in warnings)


def test_load_installed_context_unresolved_kb_entry_warns(tmp_path):
    _make_addon_dir(tmp_path, "addon_a", depends=["some_ghost_module"])
    (tmp_path / "installed_modules.txt").write_text("addon_a\nsome_ghost_module\n")

    a = _vm("addon_a", depends=["some_ghost_module"])
    with patch("oops.commands.upgrade.vanilla.load_odoo_kb", return_value={}):
        extra_depends, warnings = load_installed_context(tmp_path, [a], "14.0")

    assert extra_depends == {}
    assert any("some_ghost_module" in w and "no record in the global Odoo KB" in w for w in warnings)


def test_load_installed_context_extra_addon_at_root_warns(tmp_path):
    _make_addon_dir(tmp_path, "addon_a", depends=[])
    _make_addon_dir(tmp_path, "addon_b_not_listed", depends=[])
    (tmp_path / "installed_modules.txt").write_text("addon_a\n")

    a = _vm("addon_a", depends=[])
    with patch("oops.commands.upgrade.vanilla.load_odoo_kb", return_value={}):
        _extra_depends, warnings = load_installed_context(tmp_path, [a], "14.0")

    assert any("addon_b_not_listed" in w and "will still be removed" in w for w in warnings)


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
# build_strip_plan — orphan submodule sweep
# ---------------------------------------------------------------------------


def _add_submodule(repo: Repo, upstream_path: Path, rel_path: str) -> None:
    with repo.git.custom_environment(GIT_ALLOW_PROTOCOL="file"):
        repo.git.submodule("add", str(upstream_path), rel_path)


def _make_upstream_repo(tmp_path: Path, name: str, with_addon: bool = True) -> Path:
    upstream_path = tmp_path / name
    upstream_path.mkdir()
    upstream = Repo.init(upstream_path)
    with upstream.config_writer() as cw:
        cw.set_value("user", "email", "test@test.com")
        cw.set_value("user", "name", "Test")
    if with_addon:
        _add_local_addon(upstream_path, f"{name}_addon", author="Acme")
        upstream.index.add([f"{name}_addon"])
    else:
        (upstream_path / "README.md").write_text("no addon here\n")
        upstream.index.add(["README.md"])
    upstream.index.commit("init upstream")
    return upstream_path


def test_build_strip_plan_removes_inactive_submodule_with_no_addon(tmp_path):
    """A submodule cloned under `.third-party/` whose addon is never
    symlinked to the repo root has no discovered `VanillaModule` at all —
    `build_strip_plan` must still sweep it up as an orphan removal.
    """
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    upstream_path = _make_upstream_repo(tmp_path, "inactive_up", with_addon=True)
    (repo_path / ".third-party").mkdir()
    _add_submodule(repo, upstream_path, ".third-party/inactive_up")
    _commit_all(repo, "add inactive submodule")

    plan, _sub_by_relpath = build_strip_plan(repo, repo_path, modules=[])

    assert len(plan.actionable) == 1
    action = plan.actionable[0]
    assert action.data["kind"] == "submodule"
    assert action.data["orphan"] is True
    assert action.data["rel_path"] == ".third-party/inactive_up"


def test_build_strip_plan_removes_empty_submodule(tmp_path):
    """A submodule containing no Odoo manifest at all (e.g. a docs/tooling
    repo) has no discovered addon either — same orphan-sweep contract.
    """
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    upstream_path = _make_upstream_repo(tmp_path, "empty_up", with_addon=False)
    (repo_path / ".third-party").mkdir()
    _add_submodule(repo, upstream_path, ".third-party/empty_up")
    _commit_all(repo, "add empty submodule")

    plan, _sub_by_relpath = build_strip_plan(repo, repo_path, modules=[])

    assert len(plan.actionable) == 1
    action = plan.actionable[0]
    assert action.data["kind"] == "submodule"
    assert action.data["orphan"] is True
    assert action.data["rel_path"] == ".third-party/empty_up"


# ---------------------------------------------------------------------------
# cleanup_submodule_containers
# ---------------------------------------------------------------------------


def test_cleanup_submodule_containers_removes_empty_current_path(tmp_path):
    """`.third-party` (config.submodules.current_path) left with nothing but
    empty (former submodule) directories after every submodule is stripped
    must be removed entirely — including a nested org-level directory
    (e.g. `.third-party/OCA`) that only becomes empty once its own last
    submodule directory is gone.
    """
    (tmp_path / ".third-party" / "OCA").mkdir(parents=True)

    removed = cleanup_submodule_containers(tmp_path)

    assert removed == [".third-party"]
    assert not (tmp_path / ".third-party").exists()


def test_cleanup_submodule_containers_removes_legacy_old_path(tmp_path):
    """A legacy container from `config.submodules.old_paths` (`third-party`,
    without the leading dot) is swept up the same way as the current one.
    """
    (tmp_path / "third-party").mkdir()

    removed = cleanup_submodule_containers(tmp_path)

    assert removed == ["third-party"]
    assert not (tmp_path / "third-party").exists()


def test_cleanup_submodule_containers_leaves_non_empty_container(tmp_path):
    """A container still holding real content (e.g. a leftover submodule
    directory, or a file someone committed there directly) must not be
    touched — only genuinely empty directories are removed.
    """
    third_party = tmp_path / ".third-party"
    third_party.mkdir()
    (third_party / "still_here.txt").write_text("not a submodule\n")

    removed = cleanup_submodule_containers(tmp_path)

    assert removed == []
    assert (third_party / "still_here.txt").exists()


def test_cleanup_submodule_containers_missing_container_is_a_noop(tmp_path):
    assert cleanup_submodule_containers(tmp_path) == []


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
# bump_odoo_version / sync_project_files
# ---------------------------------------------------------------------------


def test_bump_odoo_version_writes_latest_target_image(tmp_path):
    (tmp_path / "odoo_version.txt").write_text("apik/odoo:18.0-20240101\n")
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        image = bump_odoo_version(tmp_path, "19.0")

    assert image == "apik/odoo:19.0-20260101"
    assert (tmp_path / "odoo_version.txt").read_text().strip() == "apik/odoo:19.0-20260101"


def test_bump_odoo_version_dry_run_does_not_write(tmp_path):
    (tmp_path / "odoo_version.txt").write_text("apik/odoo:18.0-20240101\n")
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        image = bump_odoo_version(tmp_path, "19.0", dry_run=True)

    assert image == "apik/odoo:19.0-20260101"
    assert (tmp_path / "odoo_version.txt").read_text().strip() == "apik/odoo:18.0-20240101"


def test_bump_odoo_version_no_image_found_raises(tmp_path):
    (tmp_path / "odoo_version.txt").write_text("apik/odoo:18.0-20240101\n")
    with patch("oops.commands.upgrade.vanilla.find_available_images", return_value=[]):
        with pytest.raises(OopsError):
            bump_odoo_version(tmp_path, "19.0")


def test_sync_project_files_skips_when_unconfigured(tmp_path):
    # conftest's MINIMAL_CONFIG leaves sync.remote_url unset by default.
    assert sync_project_files(tmp_path) == []


def test_sync_project_files_copies_from_remote(tmp_path, monkeypatch):
    from oops.core.config import config

    monkeypatch.setattr(config.sync, "remote_url", "https://example.invalid/repo.git")
    monkeypatch.setattr(config.sync, "files", {"docker-compose.yml"})

    def _fake_fetch(url, branch, files, tmpdir):
        (tmpdir / "docker-compose.yml").write_text("services: {}\n")

    with patch("oops.commands.upgrade.vanilla.fetch_project_files", side_effect=_fake_fetch):
        synced = sync_project_files(tmp_path)

    assert synced == ["docker-compose.yml"]
    assert (tmp_path / "docker-compose.yml").read_text() == "services: {}\n"


def test_sync_project_files_dry_run_lists_configured_files_only(tmp_path, monkeypatch):
    from oops.core.config import config

    monkeypatch.setattr(config.sync, "remote_url", "https://example.invalid/repo.git")
    monkeypatch.setattr(config.sync, "files", {"docker-compose.yml"})

    synced = sync_project_files(tmp_path, dry_run=True)

    assert synced == ["docker-compose.yml"]
    assert not (tmp_path / "docker-compose.yml").exists()


# ---------------------------------------------------------------------------
# CLI integration (real git repos — `main` performs real branch/commit
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
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        result = CliRunner().invoke(main, ["--to", "19.0", "--force"])

    assert result.exit_code == 0, result.output
    assert not (repo_path / "custom_mod").exists()
    script_path = repo_path / "upgrade" / "pre-uninstall_non_core_modules.py"
    assert script_path.exists()
    assert '"custom_mod"' in script_path.read_text()
    requirements = (repo_path / "requirements.txt").read_text()
    assert "odoo_upgrade @ git+https://github.com/odoo/upgrade-util@master" in requirements
    assert "git" in (repo_path / "packages.txt").read_text().split()
    assert (repo_path / "odoo_version.txt").read_text().strip() == "apik/odoo:19.0-20260101"
    assert "vanilla/19.0" in [h.name for h in repo.heads]
    assert repo.is_dirty() is False


def test_cli_kb_warning_shown_before_confirmation(tmp_path, monkeypatch):
    """Regression: the KB warning must be visible to the user before they
    decide whether to proceed — not only in the final summary, which never
    even renders if the user declines (AppAbort skips it entirely).
    """
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "custom_mod")
    _commit_all(repo, "add addon")

    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.load_odoo_kb", return_value={}):
        with patch("oops.output.workflow.prompt_confirm", return_value=False):
            result = CliRunner().invoke(main, ["--to", "19.0"])

    assert result.exit_code != 0
    assert "Global Odoo KB not found" in result.output
    assert "vanilla/19.0" not in [h.name for h in repo.heads]


def test_cli_declining_confirmation_creates_no_branch(tmp_path, monkeypatch):
    """Regression: branch creation must happen only after the user confirms —
    not while merely building/presenting the plan. Declining the "Proceed?"
    prompt must leave the repository exactly as it was: no vanilla/<to>
    branch, no stripped files, no bumped odoo_version.txt.
    """
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "custom_mod")
    _commit_all(repo, "add addon")

    before_branch = repo.active_branch.name
    before_status = repo.git.status("--porcelain")

    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        with patch("oops.output.workflow.prompt_confirm", return_value=False):
            result = CliRunner().invoke(main, ["--to", "19.0"])

    assert result.exit_code != 0
    assert repo.active_branch.name == before_branch
    assert "vanilla/19.0" not in [h.name for h in repo.heads]
    assert (repo_path / "custom_mod").exists()
    assert repo.git.status("--porcelain") == before_status


def test_cli_requires_to_version(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "custom_mod")
    _commit_all(repo, "add addon")

    monkeypatch.chdir(repo_path)
    result = CliRunner().invoke(main, ["--force"])

    assert result.exit_code != 0
    assert "--to" in result.output


def test_cli_dry_run_leaves_tree_unchanged(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "custom_mod")
    _commit_all(repo, "add addon")

    before = repo.git.status("--porcelain")
    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        result = CliRunner().invoke(main, ["--to", "19.0", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert (repo_path / "custom_mod").exists()
    assert not (repo_path / "upgrade").exists()
    assert repo.git.status("--porcelain") == before
    assert [h.name for h in repo.heads] == ["master"] or [h.name for h in repo.heads] == ["main"]


def test_cli_no_addons_exits_error(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)

    monkeypatch.chdir(repo_path)
    result = CliRunner().invoke(main, ["--to", "19.0", "--force"])

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
        with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
            result = CliRunner().invoke(main, ["--to", "19.0", "--force", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert not (repo_path / "sale_extra").exists()
    json_start = result.output.index("{")
    payload = json.loads(result.output[json_start:])
    assert payload["kb_checked"] is True
    assert payload["modules"][0]["matched_origin"] == "core"
    assert any("sale_extra" in w for w in payload["warnings"])


def test_cli_uses_installed_modules_txt_for_load_index(tmp_path, monkeypatch):
    """End-to-end regression for the reported symptom: with installed_modules.txt
    present, load_index reflects the real core dependency chain instead of
    trivially being 0/tied for every discovered addon.
    """
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "sale_extra", depends=["sale"])
    (repo_path / "installed_modules.txt").write_text("sale_extra\nsale\nbase\n")
    _commit_all(repo, "add addon and installed_modules.txt")

    fake_kb = {
        "sale": {"origin": "odoo", "depends": ["base"]},
        "base": {"origin": "odoo", "depends": []},
    }
    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.load_odoo_kb", return_value=fake_kb):
        with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
            result = CliRunner().invoke(main, ["--to", "19.0", "--force", "--format", "json"])

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    payload = json.loads(result.output[json_start:])
    assert int(payload["modules"][0]["load_index"]) > 0
    assert any("no addon at the repo root" in w for w in payload["warnings"])


def test_cli_packages_txt_merges_existing_entries(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_local_addon(repo_path, "custom_mod")
    (repo_path / "packages.txt").write_text("postgresql-client\nvim\n")
    _commit_all(repo, "add addon and packages")

    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        result = CliRunner().invoke(main, ["--to", "19.0", "--force"])

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
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        result = CliRunner().invoke(main, ["--to", "19.0", "--force"])

    assert result.exit_code == 0, result.output
    assert "Nothing to strip" not in result.output
    assert not (repo_path / "oca_mod").exists()
    assert not (repo_path / ".third-party" / "oca_mod" / ".git").exists()
    gitmodules = repo_path / ".gitmodules"
    content = gitmodules.read_text() if gitmodules.exists() else ""
    assert "oca_mod" not in content
    assert not (repo_path / ".third-party").exists()

    report_path = repo_path / ".oops" / "upgrade" / "vanilla.yml"
    report = yaml.safe_load(report_path.read_text())
    assert report["modules"][0]["name"] == "oca_mod"


def test_cli_root_level_submodule_removed_no_dangling_gitmodules(tmp_path, monkeypatch):
    """A submodule checked out directly at the repo root (no `.third-party`
    nesting, no symlink — the submodule's own root IS the addon root) is
    discovered as a "local"-looking addon per today's classification, but
    must still be removed via the submodule path, not `git rm -r`'d as a
    plain directory (which would leave `.gitmodules` dangling).
    """
    upstream_path = tmp_path / "upstream_root_mod"
    upstream_path.mkdir()
    upstream = Repo.init(upstream_path)
    with upstream.config_writer() as cw:
        cw.set_value("user", "email", "test@test.com")
        cw.set_value("user", "name", "Test")
    manifest = {"name": "my_module", "author": "Acme", "depends": []}
    (upstream_path / "__manifest__.py").write_text(repr(manifest))
    upstream.index.add(["__manifest__.py"])
    upstream.index.commit("init upstream")

    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    _add_submodule(repo, upstream_path, "my_module")
    _commit_all(repo, "add root-level submodule")

    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        result = CliRunner().invoke(main, ["--to", "19.0", "--force"])

    assert result.exit_code == 0, result.output
    assert not (repo_path / "my_module").exists()
    gitmodules = repo_path / ".gitmodules"
    content = gitmodules.read_text() if gitmodules.exists() else ""
    assert "my_module" not in content
    assert not (repo_path / ".git" / "modules" / "my_module").exists()


def test_cli_dry_run_previews_orphan_submodules(tmp_path, monkeypatch):
    """Combine an addon-backed submodule with an orphan (never-symlinked)
    one — `--dry-run` must preview both, and leave the tree untouched.
    """
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    (repo_path / ".third-party").mkdir()

    addon_upstream = _make_upstream_repo(tmp_path, "addon_up", with_addon=True)
    _add_submodule(repo, addon_upstream, ".third-party/addon_up")
    (repo_path / "addon_up_addon").symlink_to(repo_path / ".third-party" / "addon_up" / "addon_up_addon")

    orphan_upstream = _make_upstream_repo(tmp_path, "orphan_up", with_addon=True)
    _add_submodule(repo, orphan_upstream, ".third-party/orphan_up")

    _commit_all(repo, "add submodules")

    before = repo.git.status("--porcelain")
    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        result = CliRunner().invoke(main, ["--to", "19.0", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "orphan_up" in result.output
    assert repo.git.status("--porcelain") == before


def test_cli_json_output_includes_orphan_submodules(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    repo_path = Path(repo.working_tree_dir)
    (repo_path / ".third-party").mkdir()

    addon_upstream = _make_upstream_repo(tmp_path, "addon_up2", with_addon=True)
    _add_submodule(repo, addon_upstream, ".third-party/addon_up2")
    (repo_path / "addon_up2_addon").symlink_to(repo_path / ".third-party" / "addon_up2" / "addon_up2_addon")

    orphan_upstream = _make_upstream_repo(tmp_path, "orphan_up2", with_addon=True)
    _add_submodule(repo, orphan_upstream, ".third-party/orphan_up2")

    _commit_all(repo, "add submodules")

    monkeypatch.chdir(repo_path)
    with patch("oops.commands.upgrade.vanilla.find_available_images", side_effect=_fake_find_available_images):
        result = CliRunner().invoke(main, ["--to", "19.0", "--force", "--format", "json"])

    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    payload = json.loads(result.output[json_start:])
    assert payload["orphan_submodules"] == [".third-party/orphan_up2"]
    assert payload["modules"][0]["name"] == "addon_up2_addon"
