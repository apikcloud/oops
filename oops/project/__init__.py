import click

from oops.project.check import main as check
from oops.project.exclusions import main as exclude
from oops.project.info import main as info
from oops.project.update import main as update


@click.group()
def project():
    """Manage project"""


project.add_command(check)
project.add_command(update)
project.add_command(exclude)
project.add_command(info)
