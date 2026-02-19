#!/bin/bash
# Setup Nova autostart on boot
# Run: ./setup-autostart.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_FILE="$SCRIPT_DIR/nova.desktop"
AUTOSTART_DIR="$HOME/.config/autostart"

echo "Setting up Nova autostart..."

# Create autostart directory if needed
mkdir -p "$AUTOSTART_DIR"

# Copy desktop file
cp "$DESKTOP_FILE" "$AUTOSTART_DIR/nova.desktop"

# Update the Exec path to be absolute
sed -i "s|Exec=.*|Exec=$SCRIPT_DIR/nova --no-load|" "$AUTOSTART_DIR/nova.desktop"

echo "Done! Nova will start automatically on login."
echo ""
echo "To disable autostart:"
echo "  rm ~/.config/autostart/nova.desktop"
echo ""
echo "Nova will start with agent unloaded by default."
echo "Press Super+F4 to load the agent when ready."
