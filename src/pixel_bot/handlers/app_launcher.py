"""
App Launcher Handler

Launches applications by name.

Commands:
- open brave
- launch telegram
- start steam
"""
import logging
import re
import subprocess
from typing import Optional, Dict

from .base import BaseHandler

logger = logging.getLogger(__name__)


class AppLauncherHandler(BaseHandler):
    """Handles application launching."""

    # Map of app names to commands
    APP_COMMANDS: Dict[str, str] = {
        # Browsers
        "brave": "brave-browser",
        "firefox": "firefox",
        "chrome": "google-chrome",
        "chromium": "chromium-browser",

        # Communication
        "telegram": "telegram-desktop",
        "discord": "discord",
        "slack": "slack",

        # Development
        "code": "code",
        "vscode": "code",
        "visual studio code": "code",

        # Terminals
        "terminal": "tilix",
        "tilix": "tilix",
        "gnome-terminal": "gnome-terminal",

        # System
        "files": "nautilus",
        "file manager": "nautilus",
        "nautilus": "nautilus",
        "settings": "gnome-control-center",
        "pop shop": "io.elementary.appcenter",

        # VPN
        "nordvpn": "nordvpn",
        "nord vpn": "nordvpn",

        # Gaming/Emulation
        "steam": "steam",
        "pcsx2": "PCSX2",
        "mgba": "mgba-qt",

        # Audio/Video
        "audacity": "audacity",
        "vlc": "vlc",
    }

    def handle(self, query: str, speak_response: bool = True) -> str:
        """
        Handle app launch query.

        Args:
            query: User query (e.g., "open brave")
            speak_response: Whether to speak response

        Returns:
            str: Response text
        """
        try:
            # Extract app name using LLM
            app_name = self._extract_app_name(query)

            if not app_name:
                response = "I couldn't identify which app to open. Please try again."
                self._speak(response, speak_response)
                return response

            # Try to launch app
            response = self._launch_app(app_name)

            # Speak response
            self._speak(response, speak_response)

            return response

        except Exception as e:
            logger.error(f"App launcher failed: {e}", exc_info=True)
            error_msg = "Sorry, I couldn't launch that app."
            self._speak(error_msg, speak_response)
            return error_msg

    def _extract_app_name(self, query: str) -> Optional[str]:
        """
        Extract app name from query.

        Uses regex first, LLM as fallback.

        Args:
            query: User query

        Returns:
            str: App name or None
        """
        query_lower = query.lower()

        # Method 1: Direct regex matching
        # Look for "open/launch/start X"
        match = re.search(r'\b(?:open|launch|start)\s+(.+)', query_lower)
        if match:
            potential_app = match.group(1).strip()

            # Check if it's in our known apps
            for app_name in self.APP_COMMANDS.keys():
                if app_name in potential_app:
                    logger.info(f"Regex matched app: {app_name}")
                    return app_name

        # Method 2: Check for any app name in query
        for app_name in self.APP_COMMANDS.keys():
            if app_name in query_lower:
                logger.info(f"Found app in query: {app_name}")
                return app_name

        # Method 3: Use LLM to extract app name
        try:
            logger.info("Using LLM to extract app name")

            prompt = f"""Extract the application name from this user query.
The user wants to open/launch an application.

Known applications:
{', '.join(self.APP_COMMANDS.keys())}

Query: "{query}"

Respond with ONLY the application name from the list above, or "unknown" if not found.
Application:"""

            messages = [{"role": "user", "content": prompt}]
            app_name = self.llm.generate(messages, max_tokens=20, temperature=0.1).strip().lower()

            if app_name in self.APP_COMMANDS:
                logger.info(f"LLM extracted app: {app_name}")
                return app_name

            logger.warning(f"LLM returned unknown app: {app_name}")
            return None

        except Exception as e:
            logger.error(f"LLM app extraction failed: {e}")
            return None

    def _launch_app(self, app_name: str) -> str:
        """
        Launch application.

        Args:
            app_name: App name (key from APP_COMMANDS)

        Returns:
            str: Response message
        """
        command = self.APP_COMMANDS.get(app_name)

        if not command:
            logger.error(f"No command for app: {app_name}")
            return f"I don't know how to launch {app_name}"

        try:
            # Launch app in background
            subprocess.Popen(
                [command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            logger.info(f"Launched app: {app_name} ({command})")

            # Capitalize app name for response
            app_display = app_name.title()
            return f"Opening {app_display}"

        except FileNotFoundError:
            logger.error(f"App not found: {command}")
            return f"{app_name.title()} is not installed on this system"
        except Exception as e:
            logger.error(f"Failed to launch {app_name}: {e}")
            return f"Failed to launch {app_name.title()}"

    def add_app(self, app_name: str, command: str):
        """
        Add a new app to the launcher.

        Args:
            app_name: Display name
            command: Shell command to launch
        """
        self.APP_COMMANDS[app_name.lower()] = command
        logger.info(f"Added app: {app_name} -> {command}")
