import click

from oops.submodules.add import main as add
from oops.submodules.check import main as check
from oops.submodules.clean import main as clean
from oops.submodules.prune import main as prune
from oops.submodules.rewrite import main as rewrite
from oops.submodules.show import main as show
from oops.submodules.update import main as update
from oops.tools import run_script


@click.command()
@click.argument(
    "path",
    type=click.Path(exists=True, dir_okay=True, file_okay=False),
    default=".",
)
def flatten(path: str):
    output = run_script("submodules/flatten.sh", path)
    if output:
        click.echo(output)


@click.group()
def submodules():
    """Manage submodules"""


submodules.add_command(add)
submodules.add_command(check)
submodules.add_command(clean)
submodules.add_command(prune)
submodules.add_command(rewrite)
submodules.add_command(flatten)
submodules.add_command(update)
submodules.add_command(show)
