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
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.exceptions import EarlyExit
from oops.core.models import Result
from oops.core.paths import stats_file
from oops.output.formatters import FormatterRegistry, JsonFormatter, SimpleSummaryConsoleFormatter
from oops.output.sinks import deliver

from .presenters.usage import prepare

FORMATTERS: FormatterRegistry = {
    "json": JsonFormatter,
    "text": SimpleSummaryConsoleFormatter,
}


@command(name="usage", help=__doc__)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout.",
)
def main(output_format: str, output_path: Path) -> None:
    path = stats_file()
    formatter = FORMATTERS[output_format]()

    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        click.echo("No usage data found.")
        raise EarlyExit()

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
        rows.append({"scope": scope, "command": name, "count": count})

    result: Result[dict] = Result()
    result.data = {"rows": rows, "from": oldest_ts}
    outer: Result[None] = Result()

    output = prepare(result, outer, target=formatter.target)
    deliver(formatter, output, output_format, output_path)
