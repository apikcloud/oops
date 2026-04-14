# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: usage.py — oops/commands/misc/usage.py

"""
Show oops command usage counters from the local stats file.

Reads ~/.local/share/oops/stats.jsonl and prints a table of invocation
counts per command, sorted from most to least used.
"""

import json
from collections import Counter

import click
from oops.commands.base import command
from oops.core.paths import stats_file
from oops.utils.render import render_table


@command(name="usage", help=__doc__)
def main() -> None:
    path = stats_file()

    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        click.echo("No usage data found.")
        raise click.exceptions.Exit(0)

    counts: Counter = Counter()
    oldest_ts = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            cmd = event.get("cmd", "unknown")
            if cmd:
                counts[cmd] += 1
            ts = event.get("ts", "")
            if ts and (not oldest_ts or ts < oldest_ts):
                oldest_ts = ts[:10]
        except json.JSONDecodeError:
            continue

    rows = []
    for cmd, count in counts.most_common():
        parts = cmd.split(" ", 1)
        scope = parts[0] if len(parts) == 2 else ""
        name = parts[1] if len(parts) == 2 else parts[0]
        rows.append([scope, name, str(count)])
    click.echo(render_table(rows, headers=["Scope", "Command", "Count"]))
    if oldest_ts:
        click.echo(f"From: {oldest_ts}")
