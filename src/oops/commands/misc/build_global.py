# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: build_global.py — oops/commands/misc/build_global.py

"""oops misc build-kb — build the global Odoo KB (once per version).

EXPERIMENTAL — This command is part of the KB pipeline. Its interface may
change without notice between releases.

Scans Odoo community (addons/ + odoo/addons/) and enterprise sources from the
standard oops source directories (config.odoo.sources_dir/<version>/), and
produces a SQLite database stored at:

    <cache_dir>/<version>.db

where <cache_dir> defaults to ~/.cache/oops/kb/.

The global KB is version-specific and shared across all projects on the
same Odoo version — it should never be stored inside a project repository.
Run this once per Odoo version. The resulting database is shared across all
projects on the same version.
"""

from __future__ import annotations

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.logger import live_progress, log
from oops.core.models import Result
from oops.core.paths import global_kb_dir
from oops.io.file import get_odoo_sources_dirs, list_odoo_sources_versions, parse_odoo_version
from oops.kb.build import _resolve_prototype_roles, _resolve_view_types
from oops.kb.scanner import odoo_addons_roots, scan_tier
from oops.kb.store import write_global_kb
from oops.kb.xml_scanner import scan_tier_xml
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.output.sinks import deliver
from oops.services.git import require_repository
from oops.utils.render import (
    experimental_warning,
    prompt_select,
)

from .presenters.build_global import prepare

_ORIGIN_MAP = {"community": "odoo"}

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command("build-kb", help=__doc__)
@click.option(
    "--version",
    default=None,
    help=(
        "Odoo version string (e.g. 19.0). Defaults to the version declared in the current project's odoo_version.txt."
    ),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format. 'json' is suited for downstream LLM agent consumption.",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout (json) or a temp file (html).",
)
def main(
    version: str | None,
    output_format: str,
    output_path: Path | None,
) -> None:

    formatter: OutputFormatter = FORMATTERS[output_format]()
    outer: Result[None] = Result()

    experimental_warning()

    if version is None:
        try:
            _, repo_path = require_repository()
            image_info = parse_odoo_version(repo_path)
            version = str(image_info.major_version)
        except (FileNotFoundError, click.ClickException, ValueError):
            versions = [item.version for item in list_odoo_sources_versions()]
            version = prompt_select("Available version(s):", versions)

            if not version:
                raise click.UsageError(
                    "Could not detect Odoo version from odoo_version.txt. Use --version to specify it explicitly."
                ) from None

    cache_dir = global_kb_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / f"{version}.db"

    scan_results = []
    sources: dict[str, str] = {}
    result: Result[dict] = Result(
        {
            "cmd": f"Build global KB for Odoo {version}",
            "kb": {},
            "stats": [],
        }
    )

    assert result.data is not None

    # 1. Long-running processing — produces a typed Result of domain dataclasses.

    with live_progress("Building global KB..."):
        for path in get_odoo_sources_dirs(version):
            name = _ORIGIN_MAP.get(path.name, path.name)

            log.info(f"Analyzing {name.capitalize()}...")

            if not path.exists():
                continue

            for root in odoo_addons_roots(path):
                local_result: Result[dict] = scan_tier(root, name)
                for w in local_result.warnings:
                    outer.add_warning(f"[{name}] {w}")

                xml_result = scan_tier_xml(root, name)

                if local_result.data is None:
                    local_result.data = {}

                if xml_result.data is None:
                    xml_result.data = {}

                local_result.data["views"] = xml_result.data["views"]
                local_result.data["actions"] = xml_result.data["actions"]
                local_result.data["menus"] = xml_result.data["menus"]
                for w in xml_result.warnings:
                    outer.add_warning(f"[{name}] {w}")

                scan_results.append(local_result.data)
                data = local_result.data

                result.data["stats"].append(
                    {
                        "name": name,
                        "path": root,
                        "modules": len(data.get("modules", {})),
                        "symbols": len(data.get("symbols", [])),
                        "field_refs": len(data.get("field_refs", [])),
                        "origins": len(data.get("model_origins", [])),
                        "views": len(data.get("views", [])),
                        "actions": len(data.get("actions", [])),
                        "menus": len(data.get("menus", [])),
                    }
                )

            sources[name] = str(path)

        log.info("Resolving prototype roles…")
        _resolve_prototype_roles(scan_results)

        log.info("Resolving view types…")
        _resolve_view_types(scan_results)

        log.info(f"Writing file to {db_path}")
        temp_result = write_global_kb(
            db_path=db_path,
            odoo_version=version,
            sources=sources,
            scan_results=scan_results,
        )
        result.data["kb"] = temp_result.data

    # 2. Presenter prepares neutral dicts according to the formatter's audience.
    output = prepare(result, outer, target=formatter.target)
    deliver(formatter, output, output_format, output_path)
