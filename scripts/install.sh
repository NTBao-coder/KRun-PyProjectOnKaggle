#!/usr/bin/env bash
# Install only the launcher; the repository remains the source of the image.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
destination="$HOME/.local/bin/krun"
mkdir -p "$HOME/.local/bin"
if [[ -e "$destination" || -L "$destination" ]]; then
  printf 'Launcher already exists at %s; no changes made.\n' "$destination" >&2
  exit 1
fi
ln -s "$repo/bin/krun" "$destination"
printf 'Installed %s. Ensure %s/.local/bin is on PATH.\n' "$destination" "$HOME"
