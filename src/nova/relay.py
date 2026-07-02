"""
Telegram relay — the bridge between local voice and the Hermes agents.

We log in as Cole (a Telethon *user* client), send the transcribed text to an
agent's Telegram bot, and read the reply back. Because the message arrives at
the bot exactly as a normal DM, the running Hermes gateway — the single owner
of that chat's canonical session — processes it with zero race, and its answer
lands in the real Telegram thread (which we then speak aloud).

The client owns a private asyncio loop on a background thread; callers use the
synchronous ``ask()`` from any thread.
"""
import asyncio
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class RelayNotAuthorized(RuntimeError):
    """Raised when the Telethon session has no logged-in user yet."""


def assemble_reply(collected: dict, mode: str = "last") -> str:
    """
    Turn the {message_id: text} map gathered from the bot into one reply string.

    ``last``   → the final message (robust against interim status messages).
    ``concat`` → all non-empty messages joined in id order (for split answers).
    """
    parts = [collected[i].strip() for i in sorted(collected) if collected[i].strip()]
    if not parts:
        return ""
    return parts[-1] if mode == "last" else "\n\n".join(parts)


class TelegramRelay:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session: str,
        settle_s: float = 2.5,
        reply_mode: str = "last",
    ):
        self._api_id = api_id
        self._api_hash = api_hash
        self._session = session
        self._settle_s = settle_s
        if reply_mode not in ("last", "concat"):
            raise ValueError("reply_mode must be 'last' or 'concat'")
        self._reply_mode = reply_mode

        self._client = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._start_error: Optional[BaseException] = None
        self._entity_cache: dict = {}

    # ------------------------------------------------------------------ lifecycle
    def start(self, timeout: float = 30.0) -> None:
        """Start the background loop and connect using the saved session."""
        self._thread = threading.Thread(target=self._run, name="relay", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("Relay failed to start within timeout")
        if self._start_error:
            raise self._start_error

    def _run(self) -> None:
        try:
            from telethon import TelegramClient

            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            # No loop= kwarg: Telethon binds to the current loop we just set.
            self._client = TelegramClient(self._session, self._api_id, self._api_hash)

            self._loop.run_until_complete(self._client.connect())
            if not self._loop.run_until_complete(self._client.is_user_authorized()):
                # Disconnect cleanly before bailing so no background tasks dangle.
                self._disconnect_on_loop()
                self._start_error = RelayNotAuthorized(
                    "Telegram session not authorized. Run:  nova login"
                )
                self._ready.set()
                return
            logger.info("Relay connected to Telegram")
            self._ready.set()
            self._loop.run_forever()
        except BaseException as e:  # surface startup failures to start()
            self._start_error = e
            self._ready.set()
        finally:
            # run_forever has returned (normal stop). Disconnect Telethon's
            # background tasks while the loop can still run them, then close it.
            if self._client is not None and self._loop is not None:
                self._disconnect_on_loop()
                try:
                    self._loop.close()
                except Exception:
                    pass

    def _disconnect_on_loop(self) -> None:
        """
        Disconnect the client from within the loop thread.

        Telethon's ``disconnect()`` runs synchronously (returns None) when the
        loop isn't running, and returns a coroutine when it is — handle both.
        """
        try:
            if not self._client.is_connected():
                return
            res = self._client.disconnect()
            if asyncio.iscoroutine(res):
                self._loop.run_until_complete(res)
        except Exception:
            pass

    def stop(self) -> None:
        # Disconnect on the loop thread first (cancels the receiver/update
        # tasks), then stop the loop so run_forever returns and _run finishes.
        if self._loop and self._loop.is_running():
            try:
                coro = self._client.disconnect()
                if asyncio.iscoroutine(coro):
                    asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=5)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def connected(self) -> bool:
        return bool(self._client) and self._start_error is None and self._ready.is_set()

    # ------------------------------------------------------------------ ask
    def ask(self, bot: str, text: str, timeout: float = 180.0) -> str:
        """
        Send ``text`` to ``bot`` and return the agent's reply text.

        Blocks until the bot finishes answering (settle window) or ``timeout``.
        Raises on transport failure so callers can speak a fallback.
        """
        if not self.connected:
            raise RelayNotAuthorized("Relay is not connected")
        future = asyncio.run_coroutine_threadsafe(
            self._ask(bot, text, timeout), self._loop
        )
        # Give the future a little slack beyond the in-coroutine timeout.
        return future.result(timeout=timeout + 15)

    async def _resolve(self, bot: str):
        if bot not in self._entity_cache:
            # A numeric chat/user id must be passed as int; a str is treated as
            # a username. "@name" and "t.me/..." stay as strings.
            s = str(bot).strip()
            target = int(s) if s.lstrip("-").isdigit() else bot
            self._entity_cache[bot] = await self._client.get_entity(target)
        return self._entity_cache[bot]

    async def _ask(self, bot: str, text: str, timeout: float) -> str:
        entity = await self._resolve(bot)
        sent = await self._client.send_message(entity, text)
        baseline = sent.id
        logger.info("Sent to %s (msg %d): %s", bot, baseline, text[:80])

        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        collected: dict = {}      # msg_id -> latest text
        last_change: Optional[float] = None

        while True:
            # Re-read everything after our message; edits are caught because we
            # compare text each pass (Hermes streams its answer as edits).
            async for msg in self._client.iter_messages(entity, min_id=baseline, reverse=True):
                if msg.out:
                    continue
                body = msg.message or ""
                if collected.get(msg.id) != body:
                    collected[msg.id] = body
                    last_change = loop.time()

            now = loop.time()
            have_reply = any(v.strip() for v in collected.values())

            if have_reply and last_change is not None and (now - last_change) >= self._settle_s:
                break
            if now >= deadline:
                if have_reply:
                    logger.warning("Reply timeout hit; returning what we have")
                    break
                raise TimeoutError(f"No reply from {bot} within {timeout:.0f}s")

            await asyncio.sleep(0.4)

        reply = assemble_reply(collected, self._reply_mode)
        logger.info("Reply from %s: %d message(s)", bot, sum(1 for v in collected.values() if v.strip()))
        return reply
