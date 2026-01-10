"""
Desktop Notifier

Shows desktop notifications using notify-send command.
Provides visual feedback for mode changes and system status.
"""
import logging
import subprocess
from typing import Optional

from src import config

logger = logging.getLogger(__name__)


class Notifier:
    """Desktop notification manager."""

    def __init__(self):
        """Initialize notifier."""
        self.is_initialized = False
        self.app_name = config.NOTIFICATION_APP_NAME

        # Check if notify-send is available
        try:
            result = subprocess.run(
                ["which", "notify-send"],
                capture_output=True,
                timeout=2
            )
            self.is_initialized = result.returncode == 0
            if self.is_initialized:
                logger.info("Notifier initialized (using notify-send)")
            else:
                logger.warning("Notifier disabled (notify-send not found)")
        except Exception as e:
            logger.warning(f"Failed to initialize notifier: {e}")
            self.is_initialized = False

    def notify(
        self,
        title: str,
        message: str,
        icon: str = "dialog-information",
        timeout: Optional[int] = None,
        urgency: str = "normal",
    ) -> bool:
        """
        Show a desktop notification.

        Args:
            title: Notification title
            message: Notification message
            icon: Icon name (dialog-information, dialog-warning, dialog-error, audio-input-microphone, computer)
            timeout: Timeout in milliseconds (None = default)
            urgency: Urgency level (low, normal, critical)

        Returns:
            bool: True if successful
        """
        if not self.is_initialized or not config.ENABLE_NOTIFICATIONS:
            logger.debug(f"Notification skipped: {title} - {message}")
            return False

        try:
            timeout = timeout or config.NOTIFICATION_TIMEOUT

            # Use notify-send command
            cmd = [
                "notify-send",
                title,
                message,
                f"--icon={icon}",
                f"--urgency={urgency}",
                f"--app-name={self.app_name}",
                f"--expire-time={timeout}"
            ]

            subprocess.run(
                cmd,
                timeout=2,
                check=True,
                capture_output=True
            )

            logger.debug(f"Notification shown: {title}")
            return True

        except Exception as e:
            logger.error(f"Failed to show notification: {e}", exc_info=True)
            return False

    def notify_info(self, title: str, message: str) -> bool:
        """Show info notification."""
        return self.notify(title, message, icon="dialog-information")

    def notify_success(self, title: str, message: str) -> bool:
        """Show success notification."""
        return self.notify(title, message, icon="dialog-ok-apply")

    def notify_warning(self, title: str, message: str) -> bool:
        """Show warning notification."""
        return self.notify(title, message, icon="dialog-warning")

    def notify_error(self, title: str, message: str) -> bool:
        """Show error notification."""
        return self.notify(title, message, icon="dialog-error")

    # Convenience methods for common notifications
    def notify_mode_change(self, mode: str) -> bool:
        """Notify mode change."""
        mode_messages = {
            "transcribe": "🎤 Transcribe Mode Active",
            "pixel_bot": "🤖 Pixel Bot Listening",
            "cortex": "🧠 Cortex Mode Active",
            "idle": "💤 System Idle",
        }

        title = "Voice Dictation"
        message = mode_messages.get(mode, f"Mode: {mode}")

        return self.notify_info(title, message)

    def notify_models_loaded(self) -> bool:
        """Notify models loaded."""
        return self.notify_success(
            "Voice Dictation",
            "✓ Models loaded successfully"
        )

    def notify_transcription_complete(self, text: str) -> bool:
        """Notify transcription complete."""
        preview = text[:50] + "..." if len(text) > 50 else text
        return self.notify_info(
            "Transcription Complete",
            preview
        )

    def notify_error_occurred(self, error: str) -> bool:
        """Notify error occurred."""
        return self.notify_error(
            "Voice Dictation Error",
            error
        )

    # Additional notification methods for system events
    def notify_listening_started(self) -> bool:
        """Notify listening has started."""
        return self.notify(
            "Listening",
            "Say 'transcribe' or wake word to activate",
            icon="audio-input-microphone",
            urgency="low"
        )

    def notify_listening_stopped(self) -> bool:
        """Notify listening has stopped."""
        return self.notify(
            "Stopped Listening",
            "System paused",
            icon="dialog-information",
            urgency="low"
        )

    def notify_model_loaded(self, model_name: str, vram: float) -> bool:
        """
        Notify model loaded.

        Args:
            model_name: Name of the loaded model
            vram: VRAM usage in GB
        """
        return self.notify(
            "Model Loaded",
            f"{model_name} ({vram:.1f}GB VRAM)",
            icon="emblem-default",  # success icon
            urgency="normal"
        )

    def notify_model_unloaded(self, model_name: str) -> bool:
        """
        Notify model unloaded.

        Args:
            model_name: Name of the unloaded model
        """
        return self.notify(
            "Model Unloaded",
            model_name,
            icon="dialog-information",
            urgency="low"
        )

    def notify_transcribing(self, duration: Optional[float] = None) -> bool:
        """
        Notify transcription in progress.

        Args:
            duration: Audio duration in seconds (optional)
        """
        message = f"{duration:.1f}s audio" if duration else "Processing audio..."
        return self.notify(
            "Transcribing",
            message,
            icon="emblem-synchronizing",  # loading icon
            timeout=2000,
            urgency="low"
        )

    def notify_pixelbot_thinking(self) -> bool:
        """Notify Pixel Bot is thinking."""
        return self.notify(
            "Pixel Bot",
            "Thinking...",
            icon="computer",  # AI icon
            timeout=2000,
            urgency="low"
        )

    def notify_cortex_thinking(self) -> bool:
        """Notify Cortex is thinking."""
        return self.notify(
            "Cortex",
            "Querying blockchain data...",
            icon="computer",  # AI icon
            timeout=2000,
            urgency="low"
        )


# Test function
def test_notifier():
    """Test desktop notifier."""
    print("\n" + "=" * 70)
    print("DESKTOP NOTIFIER TEST")
    print("=" * 70)

    notifier = Notifier()

    if not notifier.is_initialized:
        print("\n⚠️  Notifier not available (notify2 not installed)")
        print("    Notifications will be logged only")
        print("    Install with: pip install notify2 PyGObject")
        return False

    print("\n1. Testing basic notifications...")

    notifier.notify_info("Test", "This is an info notification")
    import time
    time.sleep(1)

    notifier.notify_success("Test", "This is a success notification")
    time.sleep(1)

    notifier.notify_warning("Test", "This is a warning notification")
    time.sleep(1)

    notifier.notify_error("Test", "This is an error notification")
    time.sleep(1)

    print("\n2. Testing mode change notifications...")

    notifier.notify_mode_change("transcribe")
    time.sleep(1)

    notifier.notify_mode_change("pixel_bot")
    time.sleep(1)

    notifier.notify_mode_change("cortex")
    time.sleep(1)

    print("\n3. Testing specific notifications...")

    notifier.notify_models_loaded()
    time.sleep(1)

    notifier.notify_transcription_complete("Hello world, this is a test transcription!")
    time.sleep(1)

    print("\n" + "=" * 70)
    print("✅ NOTIFIER TEST COMPLETE")
    print("=" * 70)
    print("\nPlease verify notifications appeared on your desktop")
    print()

    return True


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run test
    test_notifier()
