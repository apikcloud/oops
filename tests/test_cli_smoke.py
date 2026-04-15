# tests/test_cli_smoke.py

from click.testing import CliRunner
from oops.cli import main


def test_cli_help():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0


def test_cli_has_command_groups():
    # Importing cli.py executes the module-level auto-discovery loop.
    # Verify that at least the expected top-level groups are registered.
    group_names = list(main.commands.keys())
    assert "addons" in group_names
    assert "submodules" in group_names


def test_cli_subgroup_help():
    result = CliRunner().invoke(main, ["addons", "--help"])
    assert result.exit_code == 0
