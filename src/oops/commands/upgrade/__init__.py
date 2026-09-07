"""Analyse, plan, and apply Odoo version upgrades."""

import click


@click.group(help="Analyse, plan, and apply Odoo version upgrades.")
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    required=False,
    default=None,
    help="GitHub token — required for upstream probing and PR operations; not needed by prepare/vanilla.",
)
@click.pass_context
def main(ctx, token):
    ctx.ensure_object(dict)
    ctx.obj["token"] = token
