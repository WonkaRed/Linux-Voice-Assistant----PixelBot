"""
Pixel Bot Client — LOCAL subprocess bridge to Pixel Bot.

No SSH overhead! OpenClaw CLI runs directly on this machine.
Response: {"result":{"payloads":[{"text":"..."}],"meta":{...}}}
"""
import json
import logging
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PixelBotResponse:
    """Response from Pixel Bot."""
    text: str
    error: Optional[str] = None
    latency: float = 0.0
    raw: dict = field(default_factory=dict)


class PixelBotClient:
    """
    Client for Pixel Bot via LOCAL subprocess.

    OpenClaw CLI runs directly on this machine — no SSH needed.
    Session continuity via --session-id keeps conversation context.
    """

    def __init__(
        self,
        agent_name: str = "main",
        session_id: str = "nova-desktop",
        timeout: int = 15,
        max_retries: int = 1,
        retry_delay: float = 2.0,
        soul_dir: Optional[Path] = None,
    ):
        self.agent_name = agent_name
        self.session_id = session_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.soul_dir = soul_dir
        self._boot_sent = False
        self._boot_message = self._load_boot_message()

        logger.info(
            f"PixelBotClient initialized: agent={agent_name}, "
            f"session={session_id}, transport=LOCAL"
        )

    def _load_boot_message(self) -> str:
        """Load boot message from soul directory or use default."""
        if self.soul_dir:
            boot_file = self.soul_dir / "boot-message.txt"
            if boot_file.exists():
                msg = boot_file.read_text().strip()
                if msg:
                    logger.info(f"Loaded boot message from {boot_file}")
                    return msg

        return (
            "Nova voice assistant active. All messages in this session are spoken "
            "aloud via TTS on Cole's desktop. Keep responses concise, conversational, "
            "and formatted for speech — no Markdown, no tables, no code blocks. "
            "Prioritize speed over depth unless explicitly asked for detail."
        )

    def send(self, message: str, context: Optional[str] = None) -> PixelBotResponse:
        """
        Send a message to Pixel Bot via local subprocess.

        On first call, prepends boot message to establish voice context.
        """
        if not message or not message.strip():
            return PixelBotResponse(text="", error="Empty message")

        full_message = message.strip()
        if context:
            full_message = (
                f"[Local data from Nova desktop]\n{context}\n\n"
                f"[User's question]\n{full_message}"
            )

        if not self._boot_sent:
            full_message = f"{self._boot_message}\n\n---\n\n{full_message}"
            self._boot_sent = True

        return self._execute(full_message)

    def _execute(self, message: str) -> PixelBotResponse:
        """Execute the local OpenClaw CLI command."""
        safe_message = shlex.quote(message)

        cli_cmd = (
            f"openclaw agent "
            f"--agent {self.agent_name} "
            f"--session-id {self.session_id} "
            f"--message {safe_message} "
            f"--json"
        )

        # bash -i to load fnm/Node.js PATH from .bashrc
        cmd = ["bash", "-i", "-c", cli_cmd]

        last_error = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = self.retry_delay * (2 ** (attempt - 1))
                logger.info(f"Retry {attempt}/{self.max_retries} after {delay:.1f}s")
                time.sleep(delay)

            try:
                logger.debug(f"Sending to Pixel Bot: {message[:80]}...")
                start = time.time()

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout + 10,
                )
                latency = time.time() - start

                # Filter stderr noise from bash -i
                stdout = result.stdout.strip()
                stderr_lines = [
                    line for line in result.stderr.strip().split('\n')
                    if line
                    and 'cannot set terminal process group' not in line
                    and 'no job control' not in line
                ]
                clean_stderr = '\n'.join(stderr_lines)

                if result.returncode != 0:
                    last_error = f"Command failed (rc={result.returncode})"
                    if clean_stderr:
                        last_error += f": {clean_stderr[:200]}"
                    logger.warning(f"Attempt {attempt + 1}: {last_error}")
                    continue

                if not stdout:
                    last_error = "Empty response from Pixel Bot"
                    logger.warning(f"Attempt {attempt + 1}: {last_error}")
                    continue

                return self._parse_response(stdout, latency)

            except subprocess.TimeoutExpired:
                last_error = f"Timed out after {self.timeout}s"
                logger.warning(f"Attempt {attempt + 1}: {last_error}")
                continue

            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected error: {e}")
                break

        logger.error(f"All attempts failed: {last_error}")
        return PixelBotResponse(text="", error=last_error)

    def _parse_response(self, stdout: str, latency: float) -> PixelBotResponse:
        """Parse the Pixel Bot JSON response."""
        # Find JSON in output (bash -i may prepend noise)
        json_start = stdout.find('{')
        if json_start > 0:
            stdout = stdout[json_start:]

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("Response was not JSON, using raw text")
            return PixelBotResponse(text=stdout.strip(), latency=latency)

        status = data.get("status", "")
        if status != "ok":
            error_msg = data.get("error", f"Status: {status}")
            return PixelBotResponse(
                text="", error=str(error_msg), latency=latency, raw=data
            )

        text = ""
        try:
            payloads = data.get("result", {}).get("payloads", [])
            if payloads:
                text = payloads[0].get("text", "")
        except (KeyError, IndexError, TypeError):
            pass

        if not text:
            logger.warning("No text in response payloads")
            return PixelBotResponse(
                text="", error="Empty response from Pixel Bot",
                latency=latency, raw=data
            )

        logger.info(f"Pixel Bot ({latency:.1f}s): {text[:100]}...")
        return PixelBotResponse(text=text, latency=latency, raw=data)

    def is_available(self) -> bool:
        """Check if OpenClaw CLI is available locally."""
        try:
            result = subprocess.run(
                ["bash", "-i", "-c", "which openclaw"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
