#!/usr/bin/env python3


import click
import libcst as cst

from osh.compat import Optional
from osh.helpers import find_addons_extended, find_manifests
from osh.parser import TypingCollector
from osh.render import human_readable
from osh.rules.__main__ import run_rules
from osh.utils import str_to_list

to_read = """
# -*- coding: utf-8 -*-
{
    "name": "APIK DATA",
    "description": "APIK DATA",
    "version": "2.0",
    "author": "Apik",
    "website": "https://www.apik.cloud",
    "category": "Vertical",
    "depends": ["base", "base_setup"],
    "data": [
        "data/ir_module_category.xml",
        "data/res_groups.xml",
        "security/ir.model.access.csv",
        "views/apik_data.xml",
        "views/apik_data_history.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "/apik_data/static/src/lib/tabulator/dist/js/tabulator.min.js",
            "/apik_data/static/src/lib/tabulator/dist/css/tabulator_simple.min.css",
            "/apik_data/static/src/lib/xlsx.mini.min.js",  # for the XLSX export
            "apik_data/static/src/js/field_tabulator.js",
        ],
        "web.assets_qweb": ["apik_data/static/src/xml/**/*"],
    },
    "installable": True,
    "application": True,
    "sequence": "0",
}
var=1

"""


@click.command(name="check")
@click.argument("path", default=".")
@click.option("--addons")
def main(path: str, addons: Optional[str] = None):
    """Check manifests by running rules on them."""

    # path = "/home/aroy/dev/repo/odoo-gaiago/third-party/apik-accounting/apik_import_fec/__manifest__.py" # noqa: E501
    # path = "/home/aroy/dev/packages/osh"

    name = "Paul"
    print(f"hello {name}!")

    options = {}
    if addons:
        options["names"] = str_to_list(addons)

    paths = []
    for manifest_path in find_manifests(path, **options):
        paths.append(manifest_path)

    click.echo(f"Searching manifests in {path}")
    click.echo(f"Paths: {human_readable(paths)}")
    run_rules(paths)

    return

    options = {}
    if addons:
        options["names"] = str_to_list(addons)
    for name, _, manifest in find_addons_extended(path, **options):  # noqa: B007
        click.echo(name)
        print("--------------")
        # print(dump(manifest))

        # visitor = TypingCollector()
        # manifest.visit(visitor)

    return

    manifest = cst.parse_module(to_read)
    visitor = TypingCollector()
    manifest.visit(visitor)

    print(visitor.errors)
    print(visitor.manifest)
