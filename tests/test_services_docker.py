"""Tests for oops.services.docker.find_available_images."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from oops.core.models import ImageInfo


def _img(image, release_date, version=19.0, enterprise=True, collection="production"):
    return ImageInfo(
        image=image,
        registry="apik",
        repository="odoo",
        major_version=version,
        release=release_date,
        enterprise=enterprise,
        collection=collection,
    )


class TestFindAvailableImagesTargetDate:
    def test_sorts_by_proximity_when_target_date_set(self):
        catalogue = [
            _img("apik/odoo:19.0-20250101-enterprise", date(2025, 1, 1)),
            _img("apik/odoo:19.0-20250601-enterprise", date(2025, 6, 1)),
            _img("apik/odoo:19.0-20251201-enterprise", date(2025, 12, 1)),
        ]
        target = date(2025, 5, 1)
        with patch("oops.services.docker.fetch_odoo_images", return_value=catalogue), patch(
            "oops.services.docker.config"
        ) as cfg:
            cfg.images.collections = ["production"]
            from oops.services.docker import find_available_images

            result = find_available_images(version=19.0, enterprise=True, target_date=target)

        # 2025-06-01 is 31d away, 2025-01-01 is 120d away, 2025-12-01 is 214d away
        assert [r.image for r in result] == [
            "apik/odoo:19.0-20250601-enterprise",
            "apik/odoo:19.0-20250101-enterprise",
            "apik/odoo:19.0-20251201-enterprise",
        ]
        assert result[0].delta == 31

    def test_no_lower_bound_filter_when_target_date_set(self):
        """target_date selection must include images older than `release`."""
        catalogue = [
            _img("apik/odoo:19.0-20240101-enterprise", date(2024, 1, 1)),
            _img("apik/odoo:19.0-20260101-enterprise", date(2026, 1, 1)),
        ]
        with patch("oops.services.docker.fetch_odoo_images", return_value=catalogue), patch(
            "oops.services.docker.config"
        ) as cfg:
            cfg.images.collections = ["production"]
            from oops.services.docker import find_available_images

            result = find_available_images(
                version=19.0,
                enterprise=True,
                release=date(2025, 1, 1),
                target_date=date(2025, 1, 1),
            )

        assert len(result) == 2

    def test_existing_behaviour_preserved_without_target_date(self):
        catalogue = [
            _img("apik/odoo:19.0-20250101-enterprise", date(2025, 1, 1)),
            _img("apik/odoo:19.0-20260101-enterprise", date(2026, 1, 1)),
        ]
        with patch("oops.services.docker.fetch_odoo_images", return_value=catalogue), patch(
            "oops.services.docker.config"
        ) as cfg:
            cfg.images.collections = ["production"]
            from oops.services.docker import find_available_images

            result = find_available_images(
                version=19.0,
                enterprise=True,
                release=date(2024, 12, 31),
            )

        # Both newer than reference, sorted descending
        assert [r.image for r in result] == [
            "apik/odoo:19.0-20260101-enterprise",
            "apik/odoo:19.0-20250101-enterprise",
        ]
        assert result[0].delta == (date(2026, 1, 1) - date(2024, 12, 31)).days

    def test_empty_catalogue_returns_empty(self):
        with patch("oops.services.docker.fetch_odoo_images", return_value=[]), patch(
            "oops.services.docker.config"
        ) as cfg:
            cfg.images.collections = ["production"]
            from oops.services.docker import find_available_images

            result = find_available_images(version=19.0, enterprise=True)

        assert result == []

    def test_collection_filter_applied(self):
        catalogue = [
            _img("apik/odoo:19.0-20250101-enterprise", date(2025, 1, 1), collection="production"),
            _img("apik/odoo:19.0-20250201-enterprise", date(2025, 2, 1), collection="staging"),
        ]
        with patch("oops.services.docker.fetch_odoo_images", return_value=catalogue), patch(
            "oops.services.docker.config"
        ) as cfg:
            cfg.images.collections = ["production"]
            from oops.services.docker import find_available_images

            result = find_available_images(version=19.0, enterprise=True)

        assert len(result) == 1
        assert result[0].collection == "production"
