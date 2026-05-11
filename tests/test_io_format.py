# ruff: noqa: E501
"""Tests for oops.io.format — formatter dispatch and text normalization."""

from unittest.mock import patch

from oops.io.format import format_file, format_python, format_xml, normalize_text

# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_strips_trailing_whitespace(self, tmp_path):
        p = tmp_path / "x.py"
        p.write_text("a = 1   \nb = 2\t\n", encoding="utf-8")
        normalize_text(p)
        assert p.read_text(encoding="utf-8") == "a = 1\nb = 2\n"

    def test_converts_crlf_to_lf(self, tmp_path):
        p = tmp_path / "x.txt"
        p.write_text("line1\r\nline2\r\n", encoding="utf-8")
        normalize_text(p)
        assert p.read_text(encoding="utf-8") == "line1\nline2\n"

    def test_adds_missing_final_newline(self, tmp_path):
        p = tmp_path / "x.txt"
        p.write_text("no newline", encoding="utf-8")
        normalize_text(p)
        assert p.read_text(encoding="utf-8") == "no newline\n"

    def test_idempotent_on_clean_file(self, tmp_path):
        p = tmp_path / "x.txt"
        original = "a\nb\n"
        p.write_text(original, encoding="utf-8")
        normalize_text(p)
        assert p.read_text(encoding="utf-8") == original

    def test_empty_file_stays_empty(self, tmp_path):
        p = tmp_path / "x.txt"
        p.write_text("", encoding="utf-8")
        normalize_text(p)
        assert p.read_text(encoding="utf-8") == ""

    def test_binary_file_unchanged(self, tmp_path):
        p = tmp_path / "x.bin"
        p.write_bytes(b"\x00\xff\x00")
        normalize_text(p)
        assert p.read_bytes() == b"\x00\xff\x00"

    def test_nonexistent_path_noop(self, tmp_path):
        normalize_text(tmp_path / "missing.txt")  # must not raise

    def test_mixed_crlf_and_trailing_whitespace(self, tmp_path):
        p = tmp_path / "x.xml"
        p.write_text("  a  \r\n  b\r\n", encoding="utf-8")
        normalize_text(p)
        assert p.read_text(encoding="utf-8") == "  a\n  b\n"


# ---------------------------------------------------------------------------
# format_python
# ---------------------------------------------------------------------------


class TestFormatPython:
    @patch("oops.io.format._has", return_value=True)
    @patch("oops.io.format.subprocess.run")
    def test_calls_ruff_format(self, mock_run, _has_mock, tmp_path):
        p = tmp_path / "x.py"
        p.write_text("a=1\n", encoding="utf-8")
        format_python(p, tmp_path)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[:2] == ["ruff", "format"]
        assert str(p) in cmd

    @patch("oops.io.format._has", return_value=True)
    @patch("oops.io.format.subprocess.run")
    def test_uses_repo_root_as_cwd(self, mock_run, _has_mock, tmp_path):
        format_python(tmp_path / "x.py", tmp_path)
        assert mock_run.call_args[1]["cwd"] == str(tmp_path)

    @patch("oops.io.format._has", return_value=False)
    @patch("oops.io.format.subprocess.run")
    def test_noop_when_ruff_missing(self, mock_run, _has_mock, tmp_path):
        format_python(tmp_path / "x.py", tmp_path)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# format_xml
# ---------------------------------------------------------------------------


class TestFormatXml:
    @patch("oops.io.format._has", return_value=True)
    @patch("oops.io.format.subprocess.run")
    def test_calls_prettier_write(self, mock_run, _has_mock, tmp_path):
        p = tmp_path / "view.xml"
        p.write_text("<odoo/>", encoding="utf-8")
        format_xml(p, tmp_path)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[:2] == ["prettier", "--write"]
        assert str(p) in cmd

    @patch("oops.io.format._has", return_value=False)
    @patch("oops.io.format.subprocess.run")
    def test_noop_when_prettier_missing(self, mock_run, _has_mock, tmp_path):
        format_xml(tmp_path / "view.xml", tmp_path)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# format_file (dispatcher)
# ---------------------------------------------------------------------------


class TestFormatFile:
    def test_skips_nonexistent_path(self, tmp_path):
        format_file(tmp_path / "missing.py", tmp_path)  # must not raise

    def test_skips_directory(self, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        format_file(d, tmp_path)  # must not raise

    @patch("oops.io.format.format_python")
    def test_dispatches_py_to_ruff(self, mock_fmt, tmp_path):
        p = tmp_path / "x.py"
        p.write_text("a=1\n", encoding="utf-8")
        format_file(p, tmp_path)
        mock_fmt.assert_called_once_with(p, tmp_path)

    @patch("oops.io.format.format_xml")
    def test_dispatches_xml_to_prettier(self, mock_fmt, tmp_path):
        p = tmp_path / "view.xml"
        p.write_text("<odoo/>\n", encoding="utf-8")
        format_file(p, tmp_path)
        mock_fmt.assert_called_once_with(p, tmp_path)

    def test_normalizes_unknown_extension(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text("key = 'val'   \n", encoding="utf-8")
        format_file(p, tmp_path)
        assert p.read_text(encoding="utf-8") == "key = 'val'\n"

    @patch("oops.io.format.format_python")
    def test_normalize_runs_after_typed_formatter(self, mock_fmt, tmp_path):
        # Even when the typed formatter is mocked (no actual file change),
        # normalize_text still runs and cleans trailing whitespace.
        p = tmp_path / "x.py"
        p.write_text("a = 1   \n", encoding="utf-8")
        format_file(p, tmp_path)
        assert p.read_text(encoding="utf-8") == "a = 1\n"
