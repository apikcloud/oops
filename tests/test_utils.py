# ruff: noqa: E501

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from tabulate import tabulate

from osh import tools
from osh.helpers import (
    clean_string,
    date_from_string,
    removesuffix,
    str_to_list,
)
from osh.io import is_pull_request_path, materialize_symlink, read_and_parse
from osh.net import parse_repository_url
from osh.render import format_datetime, human_readable, render_table
from osh.settings import DATETIME_FORMAT


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "https://github.com/oca/stock-logistics-workflow.git",
            (
                "https://github.com/oca/stock-logistics-workflow",
                "OCA",
                "stock-logistics-workflow",
            ),
        ),
        (
            "https://github.com/oca/bank-statement-import.git",
            (
                "https://github.com/oca/bank-statement-import",
                "OCA",
                "bank-statement-import",
            ),
        ),
        (
            "https://github.com/akretion/bank-statement-reconcile-simple.git",
            (
                "https://github.com/akretion/bank-statement-reconcile-simple",
                "akretion",
                "bank-statement-reconcile-simple",
            ),
        ),
        (
            "ssh://git@github.com/odoo/odoo.git",
            (
                "https://github.com/odoo/odoo",
                "odoo",
                "odoo",
            ),
        ),
        (
            "git@github.com:odoo/odoo.git",
            (
                "https://github.com/odoo/odoo",
                "odoo",
                "odoo",
            ),
        ),
        (
            "https://x-access-token:00000000@github.com/odoo/enterprise.git",
            (
                "https://github.com/odoo/enterprise",
                "odoo",
                "enterprise",
            ),
        ),
        (
            "https://user1:00000000@github.com/odoo/docker",
            (
                "https://github.com/odoo/docker",
                "odoo",
                "docker",
            ),
        ),
    ],
)
def test_parse_repository_url(raw, expected):
    assert parse_repository_url(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        [True, "yes"],
        [False, "no"],
        [1, "1"],
        [0, "0"],
        [99, "99"],
        [[1, 2, 3], "1, 2, 3"],
        ["1... 2...", "1... 2..."],
    ],
)
def test_human_readable(raw, expected):
    assert human_readable(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        [
            "Lorem,ipsum,dolor,sit,amet,",
            ["Lorem", "ipsum", "dolor", "sit", "amet"],
        ],
        [
            "1,2,3,4,5",
            ["1", "2", "3", "4", "5"],
        ],
    ],
)
def test_str_to_list(raw, expected):
    assert str_to_list(raw) == expected


def test_date_from_string():
    assert date_from_string("20250115") == date(2025, 1, 15)

    with pytest.raises(
        ValueError, match="The string does not have the correct length to be converted to a date."
    ):
        assert date_from_string("0000") == date(2025, 1, 15)


@pytest.mark.parametrize(
    "raw, expected",
    [
        [
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        ],
        [
            "  Lorem ipsum dolor sit amet, consectetur adipiscing elit. ",
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        ],
        [
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. \nNulla suscipit quam non odio accumsan pellentesque.\n",
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. \nNulla suscipit quam non odio accumsan pellentesque.",
        ],
        [None, ""],
    ],
)
def test_clean_string(raw, expected):
    assert clean_string(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        [
            "https://github.com/oca/stock-logistics-workflow.git",  # contains suffix
            "https://github.com/oca/stock-logistics-workflow",
        ],
        [
            "https://github.com/oca/stock-logistics-workflow",  # no changes
            "https://github.com/oca/stock-logistics-workflow",
        ],
    ],
)
def test_removesuffix(raw, expected):
    suffix = ".git"
    assert removesuffix(raw, suffix=suffix) == expected


# def test_read_and_parse():
#     data = [
#         [
#             "apik/odoo:15-20230103-enterprise\n",
#             ["apik/odoo:15-20230103-enterprise"],
#         ],
#         [
#             "unidecode\nxlrd\nnumpy\ncryptography\nfintech\npython-stdnum>=1.16\nnumpy-financial<=1.0.0\nxlsxwriter\n\n",
#             [
#                 "cryptography",
#                 "fintech",
#                 "numpy-financial<=1.0.0",
#                 "numpy",
#                 "python-stdnum>=1.16",
#                 "unidecode",
#                 "xlrd",
#                 "xlsxwriter",
#             ],
#         ],
#         ["# packages.txt\n", []],
#     ]

#     for item in data:
#         assert read_and_parse(item[0]) == item[1]


@pytest.mark.parametrize(
    "content, expected",
    [
        ("apik/odoo:15-20230103-enterprise\n\n", ["apik/odoo:15-20230103-enterprise"]),
        (
            "unidecode\nxlrd\nnumpy\ncryptography\nfintech\npython-stdnum>=1.16\n"
            "numpy-financial<=1.0.0\nxlsxwriter\n\n",
            [
                "cryptography",
                "fintech",
                "numpy",
                "numpy-financial<=1.0.0",
                "python-stdnum>=1.16",
                "unidecode",
                "xlrd",
                "xlsxwriter",
            ],
        ),
        ("# packages.txt\n", []),
    ],
)
def test_read_and_parse(content, expected, monkeypatch):
    def fake_read_text(self):
        return content  # string content for this parametrized case

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    assert read_and_parse(Path("whatever.txt")) == expected


def test_format_datetime_naive():
    dt = datetime(2025, 1, 15, 13, 45, 30)
    assert format_datetime(dt) == dt.strftime(DATETIME_FORMAT)


def test_format_datetime_tz_aware():
    dt = datetime(2025, 1, 15, 13, 45, 30, tzinfo=timezone.utc)
    assert format_datetime(dt) == dt.strftime(DATETIME_FORMAT)


def test_render_table_basic():
    rows = [["a", "b"], ["c", "d"]]
    expected = tabulate(rows, tablefmt="github")
    assert render_table(rows) == expected


def test_render_table_with_headers():
    rows = [[1, 2], [3, 4]]
    headers = ["A", "B"]
    expected = tabulate(rows, headers=headers, tablefmt="github")
    assert render_table(rows, headers=headers) == expected


def test_render_table_with_index():
    rows = [["x", "y"], ["u", "v"]]
    headers = ["Col1", "Col2"]
    expected = tabulate(rows, headers=headers, showindex=True, tablefmt="github")
    assert render_table(rows, headers=headers, index=True) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("PRs/123", True),  # startswith PRs/
        ("PRs/owner/repo", True),  # startswith PRs/
        ("foo/pr/bar", True),  # has a segment exactly "pr"
        ("pr", True),  # single segment equal to "pr"
        ("PRs", False),  # "PRs" without trailing slash
        ("foo/PR/bar", False),  # case-sensitive check (PR != pr)
        ("something/prs", False),  # "prs" != "pr"
        ("some/path", False),  # no pr segments and doesn't start with PRs/
        ("", False),  # empty string
    ],
)
def test_is_pull_request_path_cases(raw, expected):
    assert is_pull_request_path(raw) is expected


def test_materialize_symlink_path_not_found(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(ValueError, match=r"Path not found"):
        materialize_symlink(missing, dry_run=False)


def test_materialize_symlink_not_symlink(tmp_path):
    file_path = tmp_path / "afile"
    file_path.write_text("data")
    with pytest.raises(ValueError, match=r"Not a symlink"):
        materialize_symlink(file_path, dry_run=False)


def test_materialize_symlink_target_not_dir(tmp_path):
    target = tmp_path / "target_file.txt"
    target.write_text("content")
    link = tmp_path / "link_to_file"
    link.symlink_to(target)
    with pytest.raises(ValueError, match=r"Symlink target is not a directory"):
        materialize_symlink(link, dry_run=False)


def test_materialize_symlink_tmp_exists(tmp_path):
    target = tmp_path / "target_dir"
    target.mkdir()
    (target / "f").write_text("1")
    link = tmp_path / "mylink"
    link.symlink_to(target)
    tmp = tmp_path / f".{link.name}.__osh_materialize_tmp__"
    tmp.mkdir()  # create temporary path to trigger the error
    with pytest.raises(ValueError, match=r"Temporary path already exists"):
        materialize_symlink(link, dry_run=False)


def test_materialize_symlink_dry_run_leaves_symlink(tmp_path):
    target = tmp_path / "target_dir"
    target.mkdir()
    (target / "hello.txt").write_text("hi")
    link = tmp_path / "linkdir"
    link.symlink_to(target)
    materialize_symlink(link, dry_run=True)
    assert link.exists()
    assert link.is_symlink()
    # tmp should not exist
    tmp = tmp_path / f".{link.name}.__osh_materialize_tmp__"
    assert not tmp.exists()


def test_materialize_symlink_success_replaces_with_directory(tmp_path):
    target = tmp_path / "target_dir"
    target.mkdir()
    (target / "file.txt").write_text("payload")
    link = tmp_path / "linkdir"
    link.symlink_to(target)

    materialize_symlink(link, dry_run=False)

    # After materialization the path should be a real directory (not a symlink)
    assert link.exists()
    assert not link.is_symlink()
    assert link.is_dir()
    assert (link / "file.txt").read_text() == "payload"
    # tmp should not remain
    tmp = tmp_path / f".{link.name}.__osh_materialize_tmp__"
    assert not tmp.exists()
    # original target still exists
    assert target.exists()
    assert (target / "file.txt").read_text() == "payload"


def test_materialize_symlink_cleanup_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "target_dir"
    target.mkdir()
    (target / "a.txt").write_text("x")
    link = tmp_path / "badlink"
    link.symlink_to(target)

    tmp = tmp_path / f".{link.name}.__osh_materialize_tmp__"

    def fake_copytree(src, dst):
        # create tmp and then fail to simulate partial copy + error
        dst.mkdir()
        (dst / "partial").write_text("p")
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(tools, "copytree", fake_copytree)

    with pytest.raises(ValueError, match=r"Failed to materialize"):
        materialize_symlink(link, dry_run=False)

    # tmp must have been cleaned up by the exception handler
    assert not tmp.exists()
    # original symlink should still be present
    assert link.exists()
    assert link.is_symlink()
