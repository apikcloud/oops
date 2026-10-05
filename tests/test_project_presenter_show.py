# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)

"""Tests for the `project show` presenter and image-update formatting."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
from oops.commands.project.presenters.show import ShowPresenter
from oops.core.models import CommitInfo, ImageInfo, ProjectStatus, Result, WorkflowRunInfo
from oops.services.docker import format_image_updates, get_image_updates


def _image(release: date | None = date(2023, 1, 3), delta: int = 0) -> ImageInfo:
    return ImageInfo(
        image="acme/odoo:15.0-20230103",
        registry="acme",
        repository="odoo",
        major_version=15.0,
        release=release,
        enterprise=False,
        delta=delta,
    )


def _commit() -> CommitInfo:
    return CommitInfo(
        author="Jane Doe",
        date=datetime(2026, 6, 25, 19, 35, 55, tzinfo=timezone.utc),
        email="jane@example.com",
        message="fix: something",
        sha="6525df12",
    )


def _run() -> WorkflowRunInfo:
    return WorkflowRunInfo(
        actor="jane",
        branch="main",
        conclusion="success",
        date=datetime(2026, 6, 25, 17, 40, tzinfo=timezone.utc),
        event="push",
        name="CI",
        sha="abc123",
        status="completed",
        url="https://github.com/org/repo/actions/runs/1",
    )


def _full_status() -> ProjectStatus:
    return ProjectStatus(
        project="my_project",
        image=_image(),
        updates=[_image(release=date(2025, 1, 1), delta=729), _image(release=date(2024, 1, 1), delta=363)],
        remote_url="https://github.com/org/repo",
        branch="main",
        last_release="v1.0.0",
        next_releases={"fix": "v1.0.1", "minor": "v1.1.0", "major": "v2.0.0"},
        last_commit=_commit(),
        ci=_run(),
    )


def _data(status: ProjectStatus) -> dict:
    return ShowPresenter().to_machine(Result(data=status))["data"]


class TestShowPresenterData:
    def test_full_status_key_sets(self) -> None:
        payload = ShowPresenter().to_machine(Result(data=_full_status()))

        assert set(payload) == {"data", "warnings", "errors"}
        data = payload["data"]
        assert set(data) == {"project", "odoo", "git", "ci"}
        assert set(data["odoo"]) == {"version", "edition", "image", "updates"}
        assert set(data["odoo"]["image"]) == {"name", "registry", "release_date", "age_days"}
        assert set(data["odoo"]["updates"]) == {"available", "latest_release_date", "latest_lag_days"}
        assert set(data["git"]) == {"remote_url", "branch", "last_release", "next_releases", "last_commit"}
        assert set(data["git"]["next_releases"]) == {"fix", "minor", "major"}
        assert set(data["git"]["last_commit"]) == {"sha", "message", "author", "date"}
        assert set(data["ci"]) == {
            "name", "status", "conclusion", "branch", "sha", "actor", "event", "date", "age_days", "url",
        }

    def test_full_status_values(self) -> None:
        data = _data(_full_status())

        assert data["project"] == "my_project"
        assert data["odoo"]["version"] == "15.0"
        assert data["odoo"]["edition"] == "community"
        assert data["odoo"]["image"]["name"] == "acme/odoo:15.0-20230103"
        assert data["odoo"]["image"]["registry"] == "acme/odoo"
        assert data["odoo"]["image"]["release_date"] == "2023-01-03"
        assert isinstance(data["odoo"]["image"]["age_days"], int)
        assert data["odoo"]["updates"] == {
            "available": 2,
            "latest_release_date": "2025-01-01",
            "latest_lag_days": 729,
        }
        assert data["git"]["last_commit"]["date"] == "2026-06-25T19:35:55+00:00"
        assert data["ci"]["date"] == "2026-06-25T17:40:00+00:00"

    def test_no_image(self) -> None:
        data = _data(ProjectStatus(project="p"))

        assert data["odoo"] == {"version": None, "edition": None, "image": None, "updates": None}

    def test_image_without_release_date(self) -> None:
        data = _data(ProjectStatus(project="p", image=_image(release=None)))

        assert data["odoo"]["image"]["release_date"] is None
        assert data["odoo"]["image"]["age_days"] is None
        assert data["odoo"]["updates"] is None

    def test_up_to_date(self) -> None:
        data = _data(ProjectStatus(project="p", image=_image(), updates=[]))

        assert data["odoo"]["updates"] == {"available": 0, "latest_release_date": None, "latest_lag_days": None}

    def test_updates_unknown(self) -> None:
        data = _data(ProjectStatus(project="p", image=_image(), updates=None, updates_error=True))

        assert data["odoo"]["updates"] is None

    def test_git_and_ci_nulls(self) -> None:
        data = _data(ProjectStatus(project="p"))

        assert data["git"] == {
            "remote_url": None,
            "branch": None,
            "last_release": None,
            "next_releases": None,
            "last_commit": None,
        }
        assert data["ci"] is None


class TestShowPresenterHuman:
    def test_panels_without_ci(self) -> None:
        status = _full_status()
        status.ci = None
        layout = ShowPresenter().to_human(Result(data=status))

        assert [p.title for p in layout.panels] == ["Odoo", "Git"]
        assert [row[0] for row in layout.panels[0].values] == ["Version", "Image date", "Registry", "Update(s)"]
        assert [row[0] for row in layout.panels[1].values] == [
            "Remote",
            "Last release",
            "Next releases",
            "Last commit",
        ]

    def test_panels_with_ci(self) -> None:
        layout = ShowPresenter().to_human(Result(data=_full_status()))

        assert [p.title for p in layout.panels] == ["Odoo", "Git", "Actions"]
        assert [row[0] for row in layout.panels[2].values] == ["Last run", "Date", "URL"]

    def test_full_values(self) -> None:
        layout = ShowPresenter().to_human(Result(data=_full_status()))
        odoo = dict(layout.panels[0].values)
        git = dict(layout.panels[1].values)

        assert layout.title == "Project status - my_project"
        assert odoo["Version"] == "15.0 (community)"
        assert odoo["Image date"] == "2023-01-03"
        assert odoo["Registry"] == "acme/odoo"
        assert odoo["Update(s)"] == "2 available, latest is 729 days newer (2025-01-01)"
        assert git["Remote"] == "https://github.com/org/repo"
        assert git["Next releases"] == "minor: v1.1.0, fix: v1.0.1, major: v2.0.0"

    def test_empty_values(self) -> None:
        layout = ShowPresenter().to_human(Result(data=ProjectStatus(project="p")))
        odoo = dict(layout.panels[0].values)
        git = dict(layout.panels[1].values)

        assert odoo == {"Version": "—", "Image date": "—", "Registry": "—", "Update(s)": "-"}
        assert git == {
            "Remote": "—",
            "Last release": "—",
            "Next releases": "no valid release found",
            "Last commit": "—",
        }


class TestImageUpdates:
    @pytest.mark.parametrize(
        ("image", "available", "failed", "expected"),
        [
            (None, None, False, "-"),
            (_image(release=None), None, False, "No release date in current image tag"),
            (_image(), None, True, "Could not fetch"),
            (_image(), [], False, "Up to date"),
            (
                _image(),
                [_image(release=date(2025, 1, 1), delta=729)],
                False,
                "1 available, latest is 729 days newer (2025-01-01)",
            ),
        ],
    )
    def test_format_image_updates(self, image, available, failed, expected) -> None:  # noqa: ANN001
        assert format_image_updates(image, available, failed=failed) == expected

    def test_get_image_updates_without_image(self) -> None:
        assert get_image_updates(None) is None

    def test_get_image_updates_without_release(self) -> None:
        assert get_image_updates(_image(release=None)) is None

    def test_get_image_updates_delegates(self) -> None:
        image = _image()
        with patch("oops.services.docker.find_available_images", return_value=["x"]) as mock_find:
            assert get_image_updates(image) == ["x"]
        mock_find.assert_called_once_with(release=image.release, version=15.0, enterprise=False)
