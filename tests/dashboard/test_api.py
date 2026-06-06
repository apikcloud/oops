# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

from unittest.mock import patch

from oops.dashboard.api import Api

ENVELOPE = {
    "project check": {
        "metadata": {"command": "project check"},
        "data": [
            {"name": "mandatory_files", "label": "Mandatory files", "active": True, "status": "passed", "items": []},
        ],
        "warnings": [],
        "errors": [],
    },
    "requirements check": {
        "metadata": {"command": "requirements check"},
        "data": [
            {"name": "external", "label": "External deps", "active": True, "status": "failed", "items": ["requests"]},
        ],
        "warnings": ["w1"],
        "errors": [],
    },
    "submodules check": {
        "metadata": {"command": "submodules check"},
        "data": [{"name": "sub_urls", "label": "URLs", "active": True, "status": "skipped", "items": []}],
        "warnings": [],
        "errors": [],
    },
}

ERROR_ENVELOPE = {"metadata": {"command": "error"}, "error": "This command requires submodules."}


def _run_oops_stub(args, cwd, timeout=180):
    key = " ".join(args)
    return ENVELOPE.get(key, ERROR_ENVELOPE)


def test_check_all_assembles_sections(tmp_path):
    api = Api.__new__(Api)
    api._project_path = str(tmp_path)
    with patch("oops.dashboard.api.run_oops", side_effect=_run_oops_stub):
        result = api.check_all()

    assert result["metadata"]["command"] == "checks"
    sections = result["sections"]
    assert len(sections) == 3

    assert sections[0]["command"] == "project check"
    assert sections[0]["title"] == "Project check"
    assert sections[0]["data"] == ENVELOPE["project check"]["data"]
    assert sections[0]["error"] is None

    assert sections[1]["command"] == "requirements check"
    assert sections[1]["warnings"] == ["w1"]
    assert sections[1]["error"] is None

    assert sections[2]["command"] == "submodules check"
    assert sections[2]["data"] == ENVELOPE["submodules check"]["data"]


def test_check_all_degrades_on_error_section(tmp_path):
    """A section returning an error envelope surfaces error and empty data."""
    def stub(args, cwd, timeout=180):
        if args == ["submodules", "check"]:
            return ERROR_ENVELOPE
        return ENVELOPE.get(" ".join(args), ERROR_ENVELOPE)

    api = Api.__new__(Api)
    api._project_path = str(tmp_path)
    with patch("oops.dashboard.api.run_oops", side_effect=stub):
        result = api.check_all()

    sub_section = result["sections"][2]
    assert sub_section["error"] == "This command requires submodules."
    assert sub_section["data"] == []


def test_check_all_no_project():
    api = Api.__new__(Api)
    api._project_path = None
    result = api.check_all()
    assert result["metadata"]["command"] == "error"
    assert "no project" in result["error"]
