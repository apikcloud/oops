#!/usr/bin/env bash
set -euo pipefail

# Usage: replace-top-symlinks.sh [PATH]
# Replaces symlinks located at the top-level of PATH (default: .) with their targets.

ROOT="${1:-.}"

if [ ! -d "$ROOT" ]; then
  echo "Error: PATH '$ROOT' is not a directory." >&2
  exit 1
fi

# Replace a symlink with its target (directory or file)
replace_symlink() {
  local symlink_path="$1"

  if [ -L "$symlink_path" ]; then
    # Read the link's target as stored (may be relative)
    local target
    target="$(readlink -- "$symlink_path")"

    # If the target is relative, resolve it from the symlink's directory
    if [[ "$target" != /* ]]; then
      target="$(realpath -P -- "$(dirname -- "$symlink_path")/$target")"
    fi

    # Verify target existence
    if [ ! -e "$target" ]; then
      echo "Target $target does not exist for $symlink_path. Skipping." >&2
      return 0
    fi

    # Remove the symlink
    rm -- "$symlink_path"

    # Copy the target to the former symlink location
    if [ -d "$target" ]; then
      cp -R -- "$target" "$symlink_path"
    else
      cp -- "$target" "$symlink_path"
    fi

    echo "Replaced symlink $symlink_path with actual content from $target."
  fi
}

# Process ONLY symlinks at the top level of ROOT
find "$ROOT" -maxdepth 1 -type l -print0 | while IFS= read -r -d '' symlink; do
  replace_symlink "$symlink"
done
