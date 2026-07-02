#!/usr/bin/env bash
# Install Nova as a systemd --user service: auto-starts on login, self-restarts
# on failure, survives reboots.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$UNIT_DIR"
cp "$SCRIPT_DIR/nova.service" "$UNIT_DIR/nova.service"
systemctl --user daemon-reload
systemctl --user enable --now nova.service

echo "Installed and started nova.service."
echo "  status:  systemctl --user status nova.service"
echo "  logs:    journalctl --user -u nova.service -f"
echo "  stop:    systemctl --user stop nova.service"
echo "  disable: systemctl --user disable --now nova.service"
