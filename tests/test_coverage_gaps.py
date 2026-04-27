# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: test_coverage_gaps.py — tests/test_coverage_gaps.py

"""Targeted tests to reach the 80% coverage threshold.

Covers: io/file.py (file_updater, find_addons, find_addon_dirs,
get_requirements_diff, make_migration_command,
collect_addon_paths, get_symlink_complete_map,
get_excluded_addon_names, get_filtered_addon_names),
services/github.py (get_github_user),
"""

import pytest
from oops.core.paths import PR_DIR, UNPORTED_DIR

# ---------------------------------------------------------------------------
# Manifest fixture
# ---------------------------------------------------------------------------

MANIFEST = """\
{
    "name": "My Addon",
    "version": "17.0.1.0.0",
    "author": "Apik",
    "installable": True,
    "external_dependencies": {"python": ["requests", "xlrd"]},
    "maintainers": ["alice"],
    "summary": "A test addon",
}
"""


def _make_addon(base, name, manifest=MANIFEST):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "__manifest__.py").write_text(manifest)
    return d


# ---------------------------------------------------------------------------
# oops/io/file.py — file_updater
# ---------------------------------------------------------------------------


class TestFileUpdater:
    def test_creates_new_file_with_tags(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "config.yaml"
        file_updater(str(f), new_inner_content="content", start_tag="# s", end_tag="# e")
        assert f.exists()

    def test_full_replacement_no_tags(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "file.txt"
        f.write_text("old")
        assert file_updater(str(f), new_inner_content="new") is True
        assert "new" in f.read_text()

    def test_no_change_returns_false(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "file.txt"
        f.write_text("same")
        assert file_updater(str(f), new_inner_content="same") is False

    def test_replaces_between_tags(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "file.txt"
        f.write_text("before\n# start\nold\n# end\nafter\n")
        assert file_updater(str(f), new_inner_content="new", start_tag="# start", end_tag="# end") is True
        text = f.read_text()
        assert "new" in text
        assert "old" not in text

    def test_appends_at_bottom_when_tags_absent(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "file.txt"
        f.write_text("existing\n")
        result = file_updater(
            str(f),
            new_inner_content="appended",
            start_tag="# start",
            end_tag="# end",
            append_position="bottom",
        )
        assert result is True
        text = f.read_text()
        assert "existing" in text
        assert "appended" in text

    def test_appends_at_top_when_tags_absent(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "file.txt"
        f.write_text("existing\n")
        result = file_updater(
            str(f),
            new_inner_content="prepended",
            start_tag="# start",
            end_tag="# end",
            append_position="top",
        )
        assert result is True
        text = f.read_text()
        assert text.index("prepended") < text.index("existing")

    def test_returns_false_when_tags_absent_and_no_append(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "file.txt"
        f.write_text("no tags here")
        assert (
            file_updater(str(f), new_inner_content="x", start_tag="# s", end_tag="# e", append_position=False) is False
        )

    def test_raises_with_only_start_tag(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "file.txt"
        f.write_text("content")
        with pytest.raises(ValueError):
            file_updater(str(f), new_inner_content="x", start_tag="# s")

    def test_raises_with_only_end_tag(self, tmp_path):
        from oops.io.file import file_updater

        f = tmp_path / "file.txt"
        f.write_text("content")
        with pytest.raises(ValueError):
            file_updater(str(f), new_inner_content="x", end_tag="# e")


# ---------------------------------------------------------------------------
# oops/io/file.py — find_addons
# ---------------------------------------------------------------------------


class TestFindAddons:
    def test_yields_addon_in_root(self, tmp_path):
        from oops.io.file import find_addons

        _make_addon(tmp_path, "my_addon")
        results = list(find_addons(tmp_path))
        assert len(results) == 1
        assert results[0].technical_name == "my_addon"

    def test_shallow_skips_nested_addons(self, tmp_path):
        from oops.io.file import find_addons

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        _make_addon(subdir, "nested")
        assert list(find_addons(tmp_path, shallow=True)) == []

    def test_skips_git_dir(self, tmp_path):
        from oops.io.file import find_addons

        git_addon = tmp_path / ".git" / "addon"
        _make_addon(git_addon.parent, "addon")
        assert list(find_addons(tmp_path)) == []

    def test_skips_setup_dir(self, tmp_path):
        from oops.io.file import find_addons

        _make_addon(tmp_path / "setup", "addon")
        assert list(find_addons(tmp_path)) == []

    def test_multiple_addons(self, tmp_path):
        from oops.io.file import find_addons

        _make_addon(tmp_path, "addon_a")
        _make_addon(tmp_path, "addon_b")
        assert len(list(find_addons(tmp_path))) == 2

    def test_shallow_finds_addon_one_level_deep(self, tmp_path):
        from oops.io.file import find_addons

        # addon directly one level below root is found with shallow=True
        _make_addon(tmp_path, "addon_direct")
        results = list(find_addons(tmp_path, shallow=True))
        assert any(r.technical_name == "addon_direct" for r in results)


# ---------------------------------------------------------------------------
# oops/io/file.py — find_addon_dirs
# ---------------------------------------------------------------------------


class TestFindAddonDirs:
    def test_finds_addon_directories(self, tmp_path):
        from oops.io.file import find_addon_dirs

        _make_addon(tmp_path, "addon_x")
        result = find_addon_dirs(tmp_path)
        assert any(p.name == "addon_x" for p in result)

    def test_excludes_pr_dir_by_default(self, tmp_path):
        from oops.io.file import find_addon_dirs

        _make_addon(tmp_path / PR_DIR, "pr_addon")
        result = find_addon_dirs(tmp_path, with_pr=False)
        assert not any(PR_DIR in str(p) for p in result)

    def test_includes_pr_dir_when_requested(self, tmp_path):
        from oops.io.file import find_addon_dirs

        _make_addon(tmp_path / PR_DIR, "pr_addon")
        result = find_addon_dirs(tmp_path, with_pr=True)
        assert any(PR_DIR in str(p) for p in result)


# ---------------------------------------------------------------------------
# oops/io/file.py — make_migration_command
# ---------------------------------------------------------------------------


class TestMakeMigrationCommand:
    def test_all_lists(self):
        from oops.io.file import make_migration_command

        result = make_migration_command(
            new_addons=["addon_a"],
            updated_addons=["addon_b"],
            removed_addons=["addon_c"],
            release="1.0.0",
        )
        assert "#!/bin/bash" in result
        assert "-i addon_a" in result
        assert "-u addon_b" in result
        assert "addon_c" in result
        assert "1.0.0" in result

    def test_default_release_label(self):
        from oops.io.file import make_migration_command

        assert "Unreleased" in make_migration_command()

    def test_only_new_addons(self):
        from oops.io.file import make_migration_command

        result = make_migration_command(new_addons=["x", "y"])
        assert "-i x,y" in result
        assert "-u" not in result

    def test_only_updated_addons(self):
        from oops.io.file import make_migration_command

        result = make_migration_command(updated_addons=["z"])
        assert "-u z" in result
        assert "odoo --stop-after-init --no-http -i" not in result

    def test_only_removed_addons(self):
        from oops.io.file import make_migration_command

        result = make_migration_command(removed_addons=["gone"])
        assert "gone" in result
        assert "odoo --stop-after-init --no-http -i" not in result
        assert "-u" not in result


# ---------------------------------------------------------------------------
# oops/io/file.py — get_requirements_diff
# ---------------------------------------------------------------------------


class TestGetRequirementsDiff:
    def test_detects_new_deps(self, tmp_path):
        from oops.io.file import get_requirements_diff

        _make_addon(tmp_path, "my_addon")
        req = tmp_path / "requirements.txt"
        has_changes, new_lines, diff = get_requirements_diff(req, tmp_path)
        assert has_changes is True
        assert "requests" in new_lines
        assert "xlrd" in new_lines

    def test_no_changes_when_file_matches(self, tmp_path):
        from oops.io.file import get_requirements_diff

        _make_addon(tmp_path, "my_addon")
        # Pre-populate with what the function would generate (sorted)
        _, expected_lines, _ = get_requirements_diff(tmp_path / "req.txt", tmp_path)
        req = tmp_path / "requirements.txt"
        req.write_text("\n".join(expected_lines))
        has_changes, _, _ = get_requirements_diff(req, tmp_path)
        assert has_changes is False

    def test_no_addons_no_deps(self, tmp_path):
        from oops.io.file import get_requirements_diff

        req = tmp_path / "requirements.txt"
        has_changes, new_lines, _ = get_requirements_diff(req, tmp_path)
        # Only the header comment line
        assert len(new_lines) == 1


# ---------------------------------------------------------------------------
# oops/io/file.py — collect_addon_paths
# ---------------------------------------------------------------------------


class TestCollectAddonPaths:
    def test_lists_entries(self, tmp_path):
        from oops.io.file import collect_addon_paths

        (tmp_path / "addon_a").mkdir()
        (tmp_path / "addon_b").mkdir()
        result = collect_addon_paths(tmp_path)
        names = [p.name for p, _ in result]
        assert "addon_a" in names
        assert "addon_b" in names

    def test_marks_unported(self, tmp_path):
        from oops.io.file import collect_addon_paths

        unported = tmp_path / UNPORTED_DIR
        unported.mkdir()
        (unported / "old_addon").mkdir()
        result = collect_addon_paths(tmp_path)
        unported_entries = [(p, u) for p, u in result if u]
        assert len(unported_entries) == 1
        assert unported_entries[0][0].name == "old_addon"

    def test_regular_entries_not_marked_unported(self, tmp_path):
        from oops.io.file import collect_addon_paths

        (tmp_path / "regular").mkdir()
        result = collect_addon_paths(tmp_path)
        assert all(not u for _, u in result if _.name != UNPORTED_DIR)


# ---------------------------------------------------------------------------
# oops/io/file.py — get_symlink_complete_map
# ---------------------------------------------------------------------------


class TestGetSymlinkCompleteMap:
    def test_groups_targets_by_parent(self, tmp_path):
        from oops.io.file import get_symlink_complete_map

        target_a = tmp_path / "target_a"
        target_a.mkdir()
        target_b = tmp_path / "target_b"
        target_b.mkdir()
        link_dir = tmp_path / "links"
        link_dir.mkdir()
        (link_dir / "link_a").symlink_to(target_a)
        (link_dir / "link_b").symlink_to(target_b)
        result = get_symlink_complete_map(str(link_dir))
        # Both targets share the same parent (tmp_path)
        assert str(tmp_path) in result
        assert len(result[str(tmp_path)]) == 2

    def test_empty_dir_returns_empty_dict(self, tmp_path):
        from oops.io.file import get_symlink_complete_map

        assert get_symlink_complete_map(str(tmp_path)) == {}


# ---------------------------------------------------------------------------
# oops/services/github.py — get_github_user
# ---------------------------------------------------------------------------


class TestGetGithubUser:
    def test_returns_html_with_username(self):
        from oops.services.github import get_github_user

        result = get_github_user("alice")
        assert "alice" in result
        assert "<a " in result
        assert "<img " in result

    def test_url_contains_username(self):
        from oops.services.github import get_github_user

        result = get_github_user("bob")
        assert "https://github.com/bob" in result


# ---------------------------------------------------------------------------
# oops/io/file.py — get_excluded_addon_names / get_filtered_addon_names
# ---------------------------------------------------------------------------

THIRD_PARTY_MANIFEST = """\
{
    "name": "Third Party",
    "version": "17.0.1.0.0",
    "author": "OCA",
    "installable": True,
    "external_dependencies": {},
    "maintainers": [],
    "summary": "Third party addon",
}
"""

NON_INSTALLABLE_MANIFEST = """\
{
    "name": "WIP Addon",
    "version": "17.0.1.0.0",
    "author": "Apik",
    "installable": False,
    "external_dependencies": {},
    "maintainers": [],
    "summary": "Work in progress",
}
"""


class TestGetExcludedAddonNames:
    def test_excludes_third_party(self, tmp_path):
        from unittest.mock import patch

        from oops.io.file import get_excluded_addon_names

        _make_addon(tmp_path, "own_addon")
        _make_addon(tmp_path, "third_party", manifest=THIRD_PARTY_MANIFEST)

        with patch("oops.io.file.config") as mock_cfg:
            mock_cfg.manifest.author = "Apik"
            result = get_excluded_addon_names(tmp_path)

        assert "third_party" in result
        assert "own_addon" not in result

    def test_excludes_non_installable(self, tmp_path):
        from unittest.mock import patch

        from oops.io.file import get_excluded_addon_names

        _make_addon(tmp_path, "wip_addon", manifest=NON_INSTALLABLE_MANIFEST)

        with patch("oops.io.file.config") as mock_cfg:
            mock_cfg.manifest.author = "Apik"
            result = get_excluded_addon_names(tmp_path)

        assert "wip_addon" in result

    def test_returns_sorted(self, tmp_path):
        from unittest.mock import patch

        from oops.io.file import get_excluded_addon_names

        _make_addon(tmp_path, "zzz", manifest=THIRD_PARTY_MANIFEST)
        _make_addon(tmp_path, "aaa", manifest=THIRD_PARTY_MANIFEST)

        with patch("oops.io.file.config") as mock_cfg:
            mock_cfg.manifest.author = "Apik"
            result = get_excluded_addon_names(tmp_path)

        assert result == sorted(result)


class TestGetFilteredAddonNames:
    def test_includes_own_installable(self, tmp_path):
        from unittest.mock import patch

        from oops.io.file import get_filtered_addon_names

        _make_addon(tmp_path, "my_addon")

        with patch("oops.io.file.config") as mock_cfg:
            mock_cfg.manifest.author = "Apik"
            result = get_filtered_addon_names(tmp_path)

        assert "my_addon" in result

    def test_excludes_third_party(self, tmp_path):
        from unittest.mock import patch

        from oops.io.file import get_filtered_addon_names

        _make_addon(tmp_path, "third_party", manifest=THIRD_PARTY_MANIFEST)

        with patch("oops.io.file.config") as mock_cfg:
            mock_cfg.manifest.author = "Apik"
            result = get_filtered_addon_names(tmp_path)

        assert "third_party" not in result

    def test_excludes_non_installable(self, tmp_path):
        from unittest.mock import patch

        from oops.io.file import get_filtered_addon_names

        _make_addon(tmp_path, "wip_addon", manifest=NON_INSTALLABLE_MANIFEST)

        with patch("oops.io.file.config") as mock_cfg:
            mock_cfg.manifest.author = "Apik"
            result = get_filtered_addon_names(tmp_path)

        assert "wip_addon" not in result

    def test_excludes_symlinks(self, tmp_path):
        from unittest.mock import patch

        from oops.io.file import get_filtered_addon_names

        real = tmp_path / "src" / "my_addon"
        _make_addon(real.parent, "my_addon")
        link = tmp_path / "my_addon"
        link.symlink_to(real)

        with patch("oops.io.file.config") as mock_cfg:
            mock_cfg.manifest.author = "Apik"
            result = get_filtered_addon_names(tmp_path)

        assert "my_addon" not in result

    def test_returns_sorted(self, tmp_path):
        from unittest.mock import patch

        from oops.io.file import get_filtered_addon_names

        _make_addon(tmp_path, "zzz_addon")
        _make_addon(tmp_path, "aaa_addon")

        with patch("oops.io.file.config") as mock_cfg:
            mock_cfg.manifest.author = "Apik"
            result = get_filtered_addon_names(tmp_path)

        assert result == sorted(result)


# ---------------------------------------------------------------------------
# oops/commands/release/create.py — _update_changelog
# ---------------------------------------------------------------------------


class TestUpdateChangelog:
    from datetime import date

    TODAY = date.today().isoformat()

    CHANGELOG_WITH_UNRELEASED = """\
## [Unreleased]
- Add feature X
- Fix bug Y

## [v1.2.0] - 2026-01-01
- Previous release
"""

    CHANGELOG_PRE_EDITED = f"""\
## [v1.3.0] - {TODAY}
- Add feature X

## [v1.2.0] - 2026-01-01
- Previous release
"""

    CHANGELOG_EMPTY_UNRELEASED = """\
## [Unreleased]

## [v1.2.0] - 2026-01-01
- Previous release
"""

    CHANGELOG_NO_SECTION = """\
## [v1.2.0] - 2026-01-01
- Previous release
"""

    def test_replaces_unreleased_with_versioned_header(self):
        from oops.commands.release.create import _update_changelog

        result = _update_changelog(self.CHANGELOG_WITH_UNRELEASED, "v1.3.0")

        assert f"## [v1.3.0] - {self.TODAY}" in result
        assert "## [Unreleased]" not in result
        assert "- Add feature X" in result

    def test_version_keeps_v_prefix_in_header(self):
        from oops.commands.release.create import _update_changelog

        result = _update_changelog(self.CHANGELOG_WITH_UNRELEASED, "v1.3.0")

        assert "## [v1.3.0]" in result
        assert "## [1.3.0]" not in result

    def test_pre_edited_changelog_returned_unchanged(self):
        from oops.commands.release.create import _update_changelog

        result = _update_changelog(self.CHANGELOG_PRE_EDITED, "v1.3.0")

        assert result == self.CHANGELOG_PRE_EDITED

    def test_raises_when_no_unreleased_and_no_version_section(self):
        import click
        from oops.commands.release.create import _update_changelog

        with pytest.raises(click.ClickException, match=r"\[v1\.3\.0\]"):
            _update_changelog(self.CHANGELOG_NO_SECTION, "v1.3.0")

    def test_raises_when_section_is_empty(self):
        import click
        from oops.commands.release.create import _update_changelog

        with pytest.raises(click.ClickException, match="empty"):
            _update_changelog(self.CHANGELOG_EMPTY_UNRELEASED, "v1.3.0")
