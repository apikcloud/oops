import click

from oops.manifest.check import main as check
from oops.manifest.fix import main as fix


@click.group()
def manifest():
    """Manage manifests"""


manifest.add_command(fix)
manifest.add_command(check)
