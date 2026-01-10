"""
Hotkey Listener

Listens for global hotkeys and triggers callbacks.
- F10: Load/initialize models
- F4: START/STOP recording (push-to-talk)
"""
import logging
from typing import Callable, Optional

from pynput import keyboard

from src import config

logger = logging.getLogger(__name__)


class HotkeyListener:
    """Global hotkey listener."""

    def __init__(
        self,
        on_mount: Optional[Callable] = None,
        on_toggle: Optional[Callable] = None,
    ):
        """
        Initialize hotkey listener.

        Args:
            on_mount: Callback for F10 (mount/load models)
            on_toggle: Callback for F4 (toggle listening)
        """
        self.on_mount = on_mount
        self.on_toggle = on_toggle
        self.listener: Optional[keyboard.Listener] = None
        self.is_running = False

        logger.info("HotkeyListener initialized")

    def start(self) -> bool:
        """
        Start listening for hotkeys.

        Returns:
            bool: True if successful
        """
        if self.is_running:
            logger.warning("HotkeyListener already running")
            return True

        try:
            # Create keyboard listener
            self.listener = keyboard.Listener(
                on_press=self._on_key_press,
            )

            self.listener.start()
            self.is_running = True

            logger.info(f"✓ Hotkey listener started")
            logger.info(f"  {config.HOTKEY_MOUNT.upper()}: Load models")
            logger.info(f"  {config.HOTKEY_LISTEN.upper()}: Start/stop recording (push-to-talk)")

            return True

        except Exception as e:
            logger.error(f"Failed to start hotkey listener: {e}", exc_info=True)
            return False

    def stop(self) -> bool:
        """
        Stop listening for hotkeys.

        Returns:
            bool: True if successful
        """
        if not self.is_running:
            return True

        try:
            if self.listener:
                self.listener.stop()
                self.listener = None

            self.is_running = False
            logger.info("✓ Hotkey listener stopped")

            return True

        except Exception as e:
            logger.error(f"Failed to stop hotkey listener: {e}", exc_info=True)
            return False

    def _on_key_press(self, key):
        """
        Handle key press events.

        Args:
            key: Key that was pressed
        """
        try:
            # Convert key to string
            key_str = None

            if hasattr(key, 'name'):
                # Function keys, special keys
                key_str = key.name
            elif hasattr(key, 'char'):
                # Regular character keys
                key_str = key.char

            if not key_str:
                return

            key_str = key_str.lower()

            # Check for hotkeys
            if key_str == config.HOTKEY_MOUNT:
                logger.info(f"{config.HOTKEY_MOUNT.upper()} pressed: Loading models")
                if self.on_mount:
                    self.on_mount()

            elif key_str == config.HOTKEY_LISTEN:
                logger.info(f"{config.HOTKEY_LISTEN.upper()} pressed: Toggle recording")
                if self.on_toggle:
                    self.on_toggle()

        except Exception as e:
            logger.error(f"Error handling key press: {e}", exc_info=True)

    def get_status(self) -> dict:
        """
        Get listener status.

        Returns:
            dict: Status information
        """
        return {
            "running": self.is_running,
            "mount_key": config.HOTKEY_MOUNT,
            "toggle_key": config.HOTKEY_LISTEN,
        }


# Test function
def test_hotkey_listener():
    """Test hotkey listener."""
    print("\n" + "=" * 70)
    print("HOTKEY LISTENER TEST")
    print("=" * 70)
    print()
    print(f"Press {config.HOTKEY_MOUNT.upper()} to trigger mount callback")
    print(f"Press {config.HOTKEY_LISTEN.upper()} to trigger toggle callback")
    print("Press ESC to exit test")
    print()

    # Define callbacks
    def on_mount():
        print("✓ MOUNT callback triggered (F10 pressed)")

    def on_toggle():
        print("✓ TOGGLE callback triggered (F4 pressed)")

    # Create listener
    listener = HotkeyListener(on_mount=on_mount, on_toggle=on_toggle)

    # Start listening
    listener.start()
    print(f"Status: {listener.get_status()}")
    print("\nListening for hotkeys...\n")

    # Wait for ESC key
    try:
        with keyboard.Listener(on_press=lambda key: False if key == keyboard.Key.esc else None) as esc_listener:
            esc_listener.join()
    except KeyboardInterrupt:
        pass

    # Stop listener
    listener.stop()

    print("\n" + "=" * 70)
    print("✅ HOTKEY LISTENER TEST COMPLETE")
    print("=" * 70)

    return True


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run test
    test_hotkey_listener()
