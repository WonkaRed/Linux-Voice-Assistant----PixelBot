"""
Pixel Bot Client — SSH bridge to Pixel Bot on pixel-labs-server.

Uses SSH ControlMaster for fast connection reuse (~10ms after first call).

Transport: ssh pixel-labs-server 'bash -i -c "openclaw agent ..."'
Response:  {"result":{"payloads":[{"text":"..."}],"meta":{...}}}
"""
import logging
import subprocess
import shlex
import json
import time
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Boot message sent on first query to establish voice context
BOOT_MESSAGE = (
    "Nova voice assistant active. All messages in this session are spoken "
    "aloud via TTS on Cole's desktop. Keep responses concise, conversational, "
    "and formatted for speech — no Markdown, no tables, no code blocks. "
    "Prioritize speed over depth unless explicitly asked for detail."
)


@dataclass
class PixelBotResponse:
    """Response from Pixel Bot."""
    text: str
    error: Optional[str] = None
    latency: float = 0.0
    raw: dict = field(default_factory=dict)


class PixelBotClient:
    """
    Client for Pixel Bot via SSH.

    Uses SSH ControlMaster (configured in ~/.ssh/config as pixel-labs-server)
    for fast connection reuse (~10ms after first call vs ~500ms cold).

    Session continuity via --session-id keeps conversation context between
    voice queries. Pixel Bot's full personality, memory, and tools are active.
    """

    def __init__(
        self,
        ssh_host: str = "pixel-labs-server",
        agent_name: str = "main",
        session_id: str = "nova-desktop",
        timeout: int = 15,
        max_retries: int = 1,
        retry_delay: float = 2.0,
    ):
        self.ssh_host = ssh_host
        self.agent_name = agent_name
        self.session_id = session_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._boot_sent = False

        logger.info(
            f"PixelBotClient initialized: host={ssh_host}, "
            f"agent={agent_name}, session={session_id}"
        )

    def send(self, message: str, context: Optional[str] = None) -> PixelBotResponse:
        """
        Send a message to Pixel Bot via SSH.

        On first call, prepends a boot message to establish voice context.

        Args:
            message: The user's message text
            context: Optional local data to prepend (e.g. system stats)

        Returns:
            PixelBotResponse with text and metadata
        """
        if not message or not message.strip():
            return PixelBotResponse(text="", error="Empty message")

        # Build the full message
        full_message = message.strip()
        if context:
            full_message = (
                f"[Local data from Nova desktop]\n{context}\n\n"
                f"[User's question]\n{full_message}"
            )

        # Send boot message on first query
        if not self._boot_sent:
            full_message = f"{BOOT_MESSAGE}\n\n---\n\n{full_message}"
            self._boot_sent = True

        return self._execute(full_message)

    def _execute(self, message: str) -> PixelBotResponse:
        """Execute the SSH + CLI command."""
        safe_message = shlex.quote(message)

        # Build the CLI command
        pixelbot_cmd = (
            f"openclaw agent "
            f"--agent {self.agent_name} "
            f"--session-id {self.session_id} "
            f"--message {safe_message} "
            f"--json"
        )

        # Wrap in bash -i to load fnm/Node.js PATH
        ssh_cmd = [
            "ssh",
            self.ssh_host,
            f'bash -i -c {shlex.quote(pixelbot_cmd)}',
        ]

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
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout + 10,  # SSH timeout + buffer
                )
                latency = time.time() - start

                # Filter stderr noise from bash -i
                stdout = result.stdout.strip()
                stderr = result.stderr.strip()
                # Remove common bash -i noise
                stderr_lines = [
                    l for l in stderr.split('\n')
                    if l and 'cannot set terminal process group' not in l
                    and 'no job control' not in l
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
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # Not JSON — treat raw stdout as response text
            logger.warning("Response was not JSON, using raw text")
            return PixelBotResponse(text=stdout.strip(), latency=latency)

        # Check status
        status = data.get("status", "")
        if status != "ok":
            error_msg = data.get("error", f"Status: {status}")
            return PixelBotResponse(
                text="", error=str(error_msg), latency=latency, raw=data
            )

        # Extract text from: result.payloads[0].text
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
        """Check if Pixel Bot server is reachable via SSH."""
        try:
            result = subprocess.run(
                ["ssh", self.ssh_host, "echo pong"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "pong" in result.stdout
        except Exception:
            return False
