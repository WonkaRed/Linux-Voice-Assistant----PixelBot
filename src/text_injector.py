"""
Text Injector for X11

Types text at cursor position using pynput (X11 compatible).
Simulates keyboard input to inject transcribed text.
"""
import logging
import time
from typing import Optional

from pynput.keyboard import Controller, Key

logger = logging.getLogger(__name__)


class TextInjector:
    """Injects text via simulated keyboard input."""

    def __init__(self):
        """Initialize text injector."""
        self.keyboard = Controller()
        self.typing_delay = 0.01  # Delay between keystrokes (seconds)
        logger.info("TextInjector initialized")

    def type_text(self, text: str, delay: Optional[float] = None) -> bool:
        """
        Type text at current cursor position.

        Args:
            text: Text to type
            delay: Optional delay between characters (default: 0.01s)

        Returns:
            bool: True if successful
        """
        if not text:
            logger.warning("Empty text provided")
            return False

        try:
            delay = delay or self.typing_delay

            logger.info(f"Typing text: '{text[:50]}{'...' if len(text) > 50 else ''}'")

            # Small delay before typing to ensure focus
            time.sleep(0.1)

            # Type each character
            for char in text:
                self.keyboard.type(char)
                if delay > 0:
                    time.sleep(delay)

            logger.info("✓ Text typed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to type text: {e}", exc_info=True)
            return False

    def type_text_fast(self, text: str) -> bool:
        """
        Type text without delay (faster but may miss characters on slow systems).

        Args:
            text: Text to type

        Returns:
            bool: True if successful
        """
        return self.type_text(text, delay=0)

    def press_key(self, key: Key) -> bool:
        """
        Press a special key.

        Args:
            key: Key to press (from pynput.keyboard.Key)

        Returns:
            bool: True if successful
        """
        try:
            self.keyboard.press(key)
            self.keyboard.release(key)
            return True
        except Exception as e:
            logger.error(f"Failed to press key: {e}", exc_info=True)
            return False

    def press_enter(self) -> bool:
        """Press Enter key."""
        return self.press_key(Key.enter)

    def press_backspace(self, count: int = 1) -> bool:
        """
        Press backspace key multiple times.

        Args:
            count: Number of times to press backspace

        Returns:
            bool: True if successful
        """
        try:
            for _ in range(count):
                self.press_key(Key.backspace)
                time.sleep(0.01)
            return True
        except Exception as e:
            logger.error(f"Failed to press backspace: {e}", exc_info=True)
            return False

    def type_with_enter(self, text: str) -> bool:
        """
        Type text and press Enter.

        Args:
            text: Text to type

        Returns:
            bool: True if successful
        """
        success = self.type_text(text)
        if success:
            self.press_enter()
        return success


# Test function
def test_text_injector():
    """Test text injector (requires manual verification)."""
    print("\n" + "=" * 70)
    print("TEXT INJECTOR TEST")
    print("=" * 70)
    print("\nNOTE: This test will type text after a 3-second delay.")
    print("      Please click on a text editor (like gedit or terminal)")
    print("      within the next 3 seconds!\n")

    injector = TextInjector()

    # Countdown
    for i in range(3, 0, -1):
        print(f"Starting in {i}...")
        time.sleep(1)

    print("\n1. Testing basic typing...")
    injector.type_text("Hello from text injector!")

    time.sleep(1)
    print("\n2. Testing Enter key...")
    injector.press_enter()

    time.sleep(1)
    print("\n3. Testing fast typing...")
    injector.type_text_fast("This is typed fast!")

    time.sleep(1)
    print("\n4. Testing with Enter...")
    injector.type_with_enter("This line has Enter at the end")

    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE")
    print("=" * 70)
    print("\nPlease verify the text appeared in your editor:")
    print("  - 'Hello from text injector!'")
    print("  - 'This is typed fast!'")
    print("  - 'This line has Enter at the end'")
    print()

    return True


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run test
    test_text_injector()
