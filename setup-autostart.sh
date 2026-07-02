#!/usr/bin/env bash
# Install Nova as a login autostart entry.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"

mkdir -p "$AUTOSTART_DIR"
sed "s|^Exec=.*|Exec=$SCRIPT_DIR/nova|" "$SCRIPT_DIR/nova.desktop" > "$AUTOSTART_DIR/nova.desktop"

echo "Installed: $AUTOSTART_DIR/nova.desktop"
echo "Nova will launch on login. Remove with: rm $AUTOSTART_DIR/nova.desktop"
