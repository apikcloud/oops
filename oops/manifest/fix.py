#!/usr/bin/env python3

import os

import black
import click
from libcst.display import dump

from oops.helpers import clean_string
from oops.io import find_addons_extended, get_manifest_path
from oops.settings import (
    BLACK_MODE,
    DEFAULT_VALUES,
    FORCED_KEYS,
    HEADERS,
    REPLACEMENTS,
)


def format_manifest(data: dict) -> str:
    raw = "\n".join(HEADERS) + "\n" + repr(data)
    return black.format_str(raw, mode=BLACK_MODE)


def process_manifest(manifest: dict, force_default: bool = True):  # noqa: C901, PLR0912
    changed = False

    for key in ["mainteners", "maintener", "maintainer"]:
        if key in manifest:
            manifest["maintainers"] = manifest.pop(key)
            changed = True
            continue

    for key in ["maintainers"]:
        if key in manifest:
            val = manifest[key]

            if isinstance(val, str) and val in REPLACEMENTS:
                manifest[key] = [REPLACEMENTS[val]]
                changed = True
            elif isinstance(val, (list, tuple)):
                new_val = [REPLACEMENTS.get(v, v) for v in val]
                if new_val != val:
                    manifest[key] = new_val
                    changed = True
        elif "michel" in manifest["author"].lower():
            manifest[key] = [REPLACEMENTS["Michel GUIHENEUF"]]
            changed = True

    for key in FORCED_KEYS:
        if manifest.get(key) != DEFAULT_VALUES[key]:
            manifest[key] = DEFAULT_VALUES[key]
            changed = True

    # Cleaning up summary
    if manifest.get("summary"):
        manifest["summary"] = clean_string(manifest.get("summary"))
        changed = True

    # Remove description
    if manifest.get("description"):
        manifest.pop("description")
        changed = True
        if "summary" not in manifest:
            manifest["summary"] = clean_string(manifest.get("description"))
            changed = True

    manifest["depends"].sort()
    if "base" in manifest["depends"]:
        manifest["depends"].pop(manifest["depends"].index("base"))
        manifest["depends"].insert(0, "base")

    if force_default:
        res = {
            key: manifest.pop(key) if key in manifest and manifest.get(key) else value
            for key, value in DEFAULT_VALUES.items()
        }
        return True, res

    return changed, manifest


def save_mannifest(content: str, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        output = format_manifest(content)
        f.write(output)


@click.command(name="fix")
@click.option("--addons-dir", default=".")
def main(addons_dir):
    """Fix and standardize manifests in the given directory."""

    for name, _, manifest in find_addons_extended(addons_dir):
        click.echo(name)
        if name == "apik_data":
            click.echo(dump(manifest))
            click.echo(manifest.code)
            return

        continue

        changed, manifest = process_manifest(manifest)  # noqa: PLW2901

        if changed:
            filepath = os.path.join(addons_dir, get_manifest_path(name))
            save_mannifest(manifest, filepath)
            click.echo(f"✅ Edited {name} : {filepath}")
