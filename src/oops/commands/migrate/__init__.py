"""Analyse, plan, and apply Odoo version migrations."""

import click


@click.group(help="Analyse, plan, and apply Odoo version migrations.")
@click.option(
    "--token",
    envvar=["GH_TOKEN", "GITHUB_TOKEN"],
    required=True,
    help="GitHub token — required for upstream probing and PR operations.",
)
@click.pass_context
def main(ctx, token):
    ctx.ensure_object(dict)
    ctx.obj["token"] = token
