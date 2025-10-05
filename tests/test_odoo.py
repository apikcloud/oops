from datetime import date
from unittest.mock import patch

import pytest

from osh.docker import (
    check_image,
    fetch_odoo_images,
    find_available_images,
    parse_image_tag,
)
from osh.exceptions import DeprecatedRegistryWarning, UnusualRegistryWarning
from osh.models import ImageInfo

tags = [
    {
        "id": 805514613,
        "last_updated": "2024-12-02T11:58:19.209037Z",
        "name": "17-20241115-enterprise",
        "org": "apik",
        "repo": "dev",
        "image": "apik/dev:17-20241115-enterprise",
        "full_size": 970774538,
        "digest": "sha256:c18ecce2a194ef8aaf690b55af156655308a9afdfc98b795df7fdd17e0e502bd",
        "state": None,
        "collection": "development",
        "version": 17,
        "edition": "enterprise",
        "release": "20241115",
    },
    {
        "id": 976836335,
        "last_updated": "2025-09-21T13:03:37.077452Z",
        "name": "19.0-20250921-enterprise",
        "org": "apik",
        "repo": "odoo",
        "image": "apik/odoo:19.0-20250921-enterprise",
        "full_size": 779130948,
        "digest": "sha256:ca68c876ab9d614e27df74ec4e954d9a466c576a6a6c7c24d6ae8cde0a610683",
        "state": None,
        "collection": "production",
        "version": 19,
        "edition": "enterprise",
        "release": "20250921",
    },
    {
        "id": 976088988,
        "last_updated": "2025-09-19T12:43:25.283093Z",
        "name": "19.0-20250919-enterprise",
        "org": "apik",
        "repo": "odoo",
        "image": "apik/odoo:19.0-20250919-enterprise",
        "full_size": 779102065,
        "digest": "sha256:2b78e5a287da64272c7d1a6b0b4423b45f7d3c28daddf5b3d01e032d743a785e",
        "state": None,
        "collection": "production",
        "version": 19,
        "edition": "enterprise",
        "release": "20250919",
    },
    {
        "id": 972960574,
        "last_updated": "2025-09-15T11:13:56.322785Z",
        "name": "18.0-20250915-enterprise",
        "org": "apik",
        "repo": "odoo",
        "image": "apik/odoo:18.0-20250915-enterprise",
        "full_size": 775544703,
        "digest": "sha256:6d701f43abc49ef5fbd7d61ed8f78e4b3e36416a60ee1cb9e6bc611b45dbce55",
        "state": None,
        "collection": "production",
        "version": 18,
        "edition": "enterprise",
        "release": "20250915",
    },
]


@pytest.fixture
def mock_response():
    with patch("requests.get") as mock_get:
        yield mock_get


@pytest.fixture
def example_images():
    return [
        {
            "inputs": "loginline/odoo:15-20230103-enterprise-legacy",
            "results": ImageInfo(
                **{
                    "image": "loginline/odoo:15-20230103-enterprise-legacy",
                    "registry": "loginline",
                    "repository": "odoo",
                    "major_version": 15.0,
                    "release": date(2023, 1, 3),
                    "enterprise": True,
                    "legacy": True,
                }
            ),
        },
        {
            "inputs": "odoo:19.0-20250918",
            "results": ImageInfo(
                **{
                    "image": "odoo:19.0-20250918",
                    "registry": "odoo",
                    "repository": "odoo",
                    "major_version": 19.0,
                    "release": date(2025, 9, 18),
                    "enterprise": False,
                    "legacy": False,
                }
            ),
        },
        {
            "inputs": "odoo:19",
            "results": ImageInfo(
                **{
                    "image": "odoo:19",
                    "registry": "odoo",
                    "repository": "odoo",
                    "major_version": 19.0,
                    "release": None,
                    "enterprise": False,
                    "legacy": False,
                }
            ),
        },
        {
            "inputs": "ofleet/odoo:18-20250915",
            "results": ImageInfo(
                **{
                    "image": "ofleet/odoo:18-20250915",
                    "registry": "ofleet",
                    "repository": "odoo",
                    "major_version": 18.0,
                    "release": date(2025, 9, 15),
                    "enterprise": False,
                    "legacy": False,
                }
            ),
        },
        {
            "inputs": "apik/odoo:19.0-20250919-enterprise",
            "results": ImageInfo(
                **{
                    "image": "apik/odoo:19.0-20250919-enterprise",
                    "registry": "apik",
                    "repository": "odoo",
                    "major_version": 19.0,
                    "release": date(2025, 9, 19),
                    "enterprise": True,
                    "legacy": False,
                }
            ),
        },
    ]


def test_parse_image_tag(example_images):
    for line in example_images:
        res = parse_image_tag(line["inputs"])
        assert res == line["results"]


def test_parse_image_wrong_tag():
    tag = "19.0-20250919-enterprise"
    with pytest.raises(ValueError, match=f"Invalid image tag: {tag}"):
        parse_image_tag(tag)


def test_parse_image_without_release():
    tag = "odoo:v19"
    with pytest.raises(ValueError, match="Unrecognized tag format: v19"):
        parse_image_tag(tag)


def test_check_image():
    assert check_image(
        ImageInfo(
            **{
                "image": "apik/odoo:15-20230103-enterprise-legacy",
                "registry": "apik",
                "repository": "odoo",
                "major_version": 15.0,
                "release": date(2023, 1, 3),
                "enterprise": True,
                "legacy": True,
            }
        ),
        strict=False,
    ) == [
        f"The current Odoo image is {(date.today() - date(2023, 1, 3)).days} days old, consider updating it",
    ]


def test_check_deprecated_image():
    with pytest.warns(
        DeprecatedRegistryWarning,
    ):
        check_image(
            ImageInfo(
                **{
                    "image": "loginline/odoo:15-20230103-enterprise-legacy",
                    "registry": "loginline",
                    "repository": "odoo",
                    "major_version": 15.0,
                    "release": date(2023, 1, 3),
                    "enterprise": True,
                    "legacy": True,
                }
            )
        )


def test_check_unusual_image():
    with pytest.warns(
        UnusualRegistryWarning,
    ):
        check_image(
            ImageInfo(
                **{
                    "image": "odoo:19",
                    "registry": "odoo",
                    "repository": "odoo",
                    "major_version": 19.0,
                    "release": None,
                    "enterprise": False,
                    "legacy": False,
                }
            )
        )


def test_fetch_odoo_images_filter_on_collections(mock_response):
    # Successful response
    mock_response.return_value.json.return_value = tags
    assert fetch_odoo_images() == [
        ImageInfo.from_raw_dict(
            {
                "id": 976836335,
                "last_updated": "2025-09-21T13:03:37.077452Z",
                "name": "19.0-20250921-enterprise",
                "org": "apik",
                "repo": "odoo",
                "image": "apik/odoo:19.0-20250921-enterprise",
                "full_size": 779130948,
                "digest": "sha256:ca68c876ab9d614e27df74ec4e954d9a466c576a6a6c7c24d6ae8cde0a610683",
                "state": None,
                "collection": "production",
                "version": 19,
                "edition": "enterprise",
                "release": "20250921",
            }
        ),
        ImageInfo.from_raw_dict(
            {
                "id": 976088988,
                "last_updated": "2025-09-19T12:43:25.283093Z",
                "name": "19.0-20250919-enterprise",
                "org": "apik",
                "repo": "odoo",
                "image": "apik/odoo:19.0-20250919-enterprise",
                "full_size": 779102065,
                "digest": "sha256:2b78e5a287da64272c7d1a6b0b4423b45f7d3c28daddf5b3d01e032d743a785e",
                "state": None,
                "collection": "production",
                "version": 19,
                "edition": "enterprise",
                "release": "20250919",
            }
        ),
        ImageInfo.from_raw_dict(
            {
                "id": 972960574,
                "last_updated": "2025-09-15T11:13:56.322785Z",
                "name": "18.0-20250915-enterprise",
                "org": "apik",
                "repo": "odoo",
                "image": "apik/odoo:18.0-20250915-enterprise",
                "full_size": 775544703,
                "digest": "sha256:6d701f43abc49ef5fbd7d61ed8f78e4b3e36416a60ee1cb9e6bc611b45dbce55",
                "state": None,
                "collection": "production",
                "version": 18,
                "edition": "enterprise",
                "release": "20250915",
            }
        ),
    ]

    assert fetch_odoo_images(collections=["unknown"]) == []


def test_find_available_images(mock_response):
    release = date(2025, 9, 1)
    mock_response.return_value.json.return_value = tags
    assert find_available_images(release=release, enterprise=True, version=19.0) == [
        ImageInfo(
            **{
                "collection": "production",
                "delta": (date(2025, 9, 21) - release).days,
                "enterprise": True,
                "image": "apik/odoo:19.0-20250921-enterprise",
                "major_version": 19.0,
                "registry": "apik",
                "release": date(2025, 9, 21),
                "repository": "odoo",
            }
        ),
        ImageInfo(
            **{
                "collection": "production",
                "delta": (date(2025, 9, 19) - release).days,
                "enterprise": True,
                "image": "apik/odoo:19.0-20250919-enterprise",
                "major_version": 19.0,
                "registry": "apik",
                "release": date(2025, 9, 19),
                "repository": "odoo",
            }
        ),
    ]

    assert find_available_images(release=release, enterprise=True, version=20.0) == []
