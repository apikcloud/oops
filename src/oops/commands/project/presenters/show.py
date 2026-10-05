# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — src/oops/commands/project/presenters/show.py

from __future__ import annotations

from oops.core.models import ProjectStatus, Result
from oops.output.base import SimplePresenter
from oops.output.layout import ConclusionBlock, MetricsLayout, MetricsPanelBlock
from oops.services.docker import format_image_updates
from oops.utils.render import format_datetime
from oops_engine.compat import List, Optional


def _odoo(status: ProjectStatus) -> dict:
    image = status.image
    if image is None:
        return {"version": None, "edition": None, "image": None, "updates": None}

    updates = None
    if status.updates is not None:
        latest = status.updates[0] if status.updates else None
        updates = {
            "available": len(status.updates),
            "latest_release_date": latest.release.isoformat() if latest and latest.release else None,
            "latest_lag_days": latest.delta if latest else None,
        }

    return {
        "version": str(image.major_version),
        "edition": image.edition,
        "image": {
            "name": image.image,
            "registry": image.source,
            "release_date": image.release.isoformat() if image.release else None,
            "age_days": image.age,
        },
        "updates": updates,
    }


def _git(status: ProjectStatus) -> dict:
    commit = status.last_commit
    return {
        "remote_url": status.remote_url,
        "branch": status.branch,
        "last_release": status.last_release,
        "next_releases": status.next_releases,
        "last_commit": {
            "sha": commit.sha,
            "message": commit.message,
            "author": commit.author,
            "date": commit.date.isoformat(),
        }
        if commit
        else None,
    }


def _ci(status: ProjectStatus) -> Optional[dict]:
    run = status.ci
    if run is None:
        return None
    return {
        "name": run.name,
        "status": run.status,
        "conclusion": run.conclusion,
        "branch": run.branch,
        "sha": run.sha,
        "actor": run.actor,
        "event": run.event,
        "date": run.date.isoformat(),
        "age_days": run.age,
        "url": run.url,
    }


def _odoo_rows(status: ProjectStatus) -> List[List[str]]:
    image = status.image
    return [
        ["Version", f"{image.major_version} ({image.edition})" if image else "—"],
        ["Image date", image.release.isoformat() if image and image.release else "—"],
        ["Registry", image.source if image else "—"],
        ["Update(s)", format_image_updates(image, status.updates, failed=status.updates_error)],
    ]


def _git_rows(status: ProjectStatus) -> List[List[str]]:
    releases = status.next_releases
    return [
        ["Remote", status.remote_url or "—"],
        ["Last release", status.last_release or "—"],
        [
            "Next releases",
            f"minor: {releases['minor']}, fix: {releases['fix']}, major: {releases['major']}"
            if releases
            else "no valid release found",
        ],
        ["Last commit", str(status.last_commit) if status.last_commit else "—"],
    ]


def _ci_rows(status: ProjectStatus) -> List[List[str]]:
    run = status.ci
    assert run is not None
    return [
        ["Last run", str(run)],
        ["Date", f"{format_datetime(run.date)} ({run.age} days ago)"],
        ["URL", run.url],
    ]


class ShowPresenter(SimplePresenter[ProjectStatus]):
    def to_data(self, result: Result[ProjectStatus]) -> dict:
        status = result.unwrap
        return {
            "project": status.project,
            "odoo": _odoo(status),
            "git": _git(status),
            "ci": _ci(status),
        }

    def to_human(self, result: Result[ProjectStatus]) -> MetricsLayout:
        status = result.unwrap

        panels = [
            MetricsPanelBlock("Odoo", _odoo_rows(status)),
            MetricsPanelBlock("Git", _git_rows(status)),
        ]
        if status.ci:
            panels.append(MetricsPanelBlock("Actions", _ci_rows(status)))

        return MetricsLayout(
            title=f"Project status - {status.project}",
            panels=panels,
            conclusion=ConclusionBlock(True, "Status report"),
            warnings=result.warnings,
            errors=result.errors,
        )
