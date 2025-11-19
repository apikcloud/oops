import click

from oops.addons import addons
from oops.manifest import manifest
from oops.project import project
from oops.submodules import submodules


@click.group()
def main():
    """Odoo Scripts & Heplers (oops) - Manage Odoo projects with ease."""


main.add_command(addons)
main.add_command(manifest)
main.add_command(submodules)
main.add_command(project)
