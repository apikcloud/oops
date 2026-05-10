# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from __future__ import annotations

from datetime import datetime, timezone

from oops.io.installed_modules import InstalledModules, read_installed_modules


class TestReadInstalledModules:
    def test_missing_file_returns_none(self, tmp_path):
        result = read_installed_modules(tmp_path)
        assert result is None

    def test_empty_file(self, tmp_path):
        (tmp_path / "installed_modules.txt").write_text("", encoding="utf-8")
        result = read_installed_modules(tmp_path)
        assert isinstance(result, InstalledModules)
        assert result.modules == []
        assert result.generated_by is None
        assert result.generated_at is not None
        # Falls back to mtime
        mtime = datetime.fromtimestamp(
            (tmp_path / "installed_modules.txt").stat().st_mtime, tz=timezone.utc
        )
        assert abs((result.generated_at - mtime).total_seconds()) < 1

    def test_only_generated_at_header(self, tmp_path):
        content = "# generated_at: 2026-05-09T11:46:14Z\n"
        (tmp_path / "installed_modules.txt").write_text(content, encoding="utf-8")
        result = read_installed_modules(tmp_path)
        assert result is not None
        assert result.modules == []
        assert result.generated_at == datetime(2026, 5, 9, 11, 46, 14, tzinfo=timezone.utc)

    def test_bad_timestamp_falls_back_to_mtime(self, tmp_path):
        content = "# generated_at: not-a-date\nsome_module\n"
        p = tmp_path / "installed_modules.txt"
        p.write_text(content, encoding="utf-8")
        result = read_installed_modules(tmp_path)
        assert result is not None
        assert result.modules == ["some_module"]
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        assert abs((result.generated_at - mtime).total_seconds()) < 1

    def test_plain_comments_ignored(self, tmp_path):
        content = (
            "# generated_at: 2026-05-09T00:00:00Z\n"
            "# This is a plain comment\n"
            "module_a\n"
            "# another comment\n"
            "module_b\n"
        )
        (tmp_path / "installed_modules.txt").write_text(content, encoding="utf-8")
        result = read_installed_modules(tmp_path)
        assert result is not None
        assert result.modules == ["module_a", "module_b"]

    def test_duplicate_modules_deduped_order_preserved(self, tmp_path):
        content = "module_a\nmodule_b\nmodule_a\nmodule_c\nmodule_b\n"
        (tmp_path / "installed_modules.txt").write_text(content, encoding="utf-8")
        result = read_installed_modules(tmp_path)
        assert result is not None
        assert result.modules == ["module_a", "module_b", "module_c"]

    def test_trailing_whitespace_and_blank_lines(self, tmp_path):
        content = "\n  module_a  \n\n  module_b  \n\n"
        (tmp_path / "installed_modules.txt").write_text(content, encoding="utf-8")
        result = read_installed_modules(tmp_path)
        assert result is not None
        assert result.modules == ["module_a", "module_b"]

    def test_generated_by_parsed(self, tmp_path):
        content = (
            "# generated_at: 2026-05-09T12:00:00Z\n"
            "# generated_by: oops v1.0\n"
            "module_x\n"
        )
        (tmp_path / "installed_modules.txt").write_text(content, encoding="utf-8")
        result = read_installed_modules(tmp_path)
        assert result is not None
        assert result.generated_by == "oops v1.0"
        assert result.modules == ["module_x"]

    def test_path_is_absolute(self, tmp_path):
        (tmp_path / "installed_modules.txt").write_text("module_a\n", encoding="utf-8")
        result = read_installed_modules(tmp_path)
        assert result is not None
        assert result.path.is_absolute()
        assert result.path == (tmp_path / "installed_modules.txt")
