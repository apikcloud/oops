# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: sinks.py — src/oops/output/sinks.py

"""Output sinks: where formatter content goes.

The formatter produces a string. This module decides where that string
lands (stdout, given path, or temp file with browser).

Each format declares its own policy (default sink, suffix, browser).
"""

from __future__ import annotations

import os
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import click
from oops.output.base import OutputFormatter
from oops.output.layout import Output
from oops.utils.compat import Literal, Optional

DefaultSink = Literal["stdout", "tempfile"]


@dataclass(frozen=True)
class SinkPolicy:
    """How a given output format is delivered when no path is provided.

    Attributes:
        default: where the content goes if `output_path` is None.
            - "stdout": print the content (parsable by jq, etc.).
            - "tempfile": write to a temporary file.
        suffix: file extension used for temp files and reported paths.
        open_browser: open the file in the default browser when written
            to a temp file. Ignored when `output_path` is provided.
    """

    default: DefaultSink
    suffix: str
    open_browser: bool = False


SINK_POLICIES: dict[str, SinkPolicy] = {
    "json": SinkPolicy(default="stdout", suffix=".json", open_browser=False),
    "html": SinkPolicy(default="tempfile", suffix=".html", open_browser=True),
    "csv": SinkPolicy(default="stdout", suffix=".csv", open_browser=False),
}


def write_output(
    content: str,
    output_format: str,
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """Deliver `content` according to the format's policy.

    Args:
        content: the rendered output as a string.
        output_format: format key registered in SINK_POLICIES.
        output_path: explicit destination. When provided, always writes
            to that path and skips browser opening.

    Returns:
        The path written to, or None if printed to stdout.
    """
    policy = SINK_POLICIES.get(output_format)
    if policy is None:
        raise ValueError(f"Unsupported output format: {output_format}")

    # Explicit path always wins, regardless of the format's default sink.
    if output_path is not None:
        output_path.write_text(content, encoding="utf-8")
        return output_path

    if policy.default == "stdout":
        print(content)
        return None

    # default == "tempfile"
    fd, tmp = tempfile.mkstemp(suffix=policy.suffix)
    os.close(fd)
    path = Path(tmp)
    path.write_text(content, encoding="utf-8")

    if policy.open_browser:
        webbrowser.open(path.as_uri())

    return path


def deliver(
    formatter: OutputFormatter,
    output: Output,
    output_format: str,
    output_path: Optional[Path],
) -> None:
    """Render then route: human formatters return None; machine formatters
    return a string sent through write_output."""
    content = formatter.render(output)
    if content is not None:
        path = write_output(content, output_format, output_path)
        if path is not None:
            click.echo(f"Report written to {path}", err=True)
