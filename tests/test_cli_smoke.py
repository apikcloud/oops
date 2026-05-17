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


def test_misc_build_kb_help():
    """Regression guard: build-kb --help must not raise (catches API-shape breaks)."""
    result = CliRunner().invoke(main, ["misc", "build-kb", "--help"])
    assert result.exit_code == 0


def test_misc_create_workspace_help():
    """Regression guard: create-workspace --help must not raise."""
    result = CliRunner().invoke(main, ["misc", "create-workspace", "--help"])
    assert result.exit_code == 0
