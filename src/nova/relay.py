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

# Hermes marks a message "being worked on" with a \U0001f440 (eyes) reaction,
# then swaps it for \U0001f44d/\U0001f44e (thumbs up/down) — or clears it on
# cancellation — only *after* every reply for that turn has already been sent
# (gateway/platforms/base.py: on_processing_complete runs after delivery).
# That ordering makes the reaction flip a stronger "done" signal than a fixed
# silence window: a tool call (web search, a slow shell command) can go quiet
# for longer than any reasonable settle_s while Hermes is still working, which
# used to make us return the tool-status bubble instead of the real answer.
# Requires TELEGRAM_REACTIONS=true on the Hermes gateway; if that's unset (or
# the bot can't react in this chat) no reaction ever appears and we fall back
# to the settle_s heuristic exactly as before — pure opportunistic upgrade.
REACTION_IN_PROGRESS = "\U0001f440"
REACTIONS_TERMINAL = {"\U0001f44d", "\U0001f44e"}


class RelayNotAuthorized(RuntimeError):
    """Raised when the Telethon session has no logged-in user yet."""


class ReactionTracker:
    """Tracks one message's Hermes processing-lifecycle reaction.

    Feed it the set of reaction emoji currently on the triggering message
    (from successive polls); ``done`` latches True once Hermes signals the
    turn is over — a terminal reaction, or the in-progress one clearing
    without ever becoming terminal (a cancelled run). Never resets once done.
    """

    def __init__(self):
        self._saw_in_progress = False
        self.done = False

    def update(self, emojis: set) -> bool:
        if self.done:
            return True
        if emojis & REACTIONS_TERMINAL:
            self.done = True
        elif REACTION_IN_PROGRESS in emojis:
            self._saw_in_progress = True
        elif self._saw_in_progress and not emojis:
            self.done = True  # cleared after in-progress => cancelled/finished
        return self.done


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
            # connection_retries=None => retry forever. This runs unattended
            # for weeks (sleep/wake, wifi/VPN changes, server reboots); the
            # default of 5 retries then giving up would leave the relay
            # silently dead until someone noticed and restarted the service.
            self._client = TelegramClient(
                self._session, self._api_id, self._api_hash,
                connection_retries=None, retry_delay=1,
            )

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

    @staticmethod
    def _reaction_emojis_of(msg) -> set:
        """Emoji currently on a Telethon message, or {} if it has none."""
        reactions = getattr(msg, "reactions", None)
        if not reactions or not reactions.results:
            return set()
        out = set()
        for r in reactions.results:
            emo = getattr(r.reaction, "emoticon", None)
            if emo:
                out.add(emo)
        return out

    async def _ask(self, bot: str, text: str, timeout: float) -> str:
        entity = await self._resolve(bot)
        sent = await self._client.send_message(entity, text)
        baseline = sent.id
        logger.info("Sent to %s (msg %d): %s", bot, baseline, text[:80])

        loop = asyncio.get_event_loop()
        t_send = loop.time()
        deadline = t_send + timeout
        collected: dict = {}      # msg_id -> latest text
        last_change: Optional[float] = None
        reactions = ReactionTracker()
        t_first_reply: Optional[float] = None   # when the bot's first text landed
        reason = "?"

        while True:
            # Re-read everything from our own message onward in one call:
            # min_id=baseline-1 also picks up the baseline message itself, so
            # we can read its reaction lifecycle (see module docstring) for
            # free instead of issuing a second, separately-rate-limited API
            # call every poll — Telegram flood-waits a chat that polls two
            # methods every ~0.4s over a multi-minute tool-using turn.
            async for msg in self._client.iter_messages(entity, min_id=baseline - 1, reverse=True):
                if msg.id == baseline:
                    reactions.update(self._reaction_emojis_of(msg))
                    continue
                if msg.out:
                    continue
                body = msg.message or ""
                if collected.get(msg.id) != body:
                    collected[msg.id] = body
                    last_change = loop.time()

            now = loop.time()
            have_reply = any(v.strip() for v in collected.values())
            if have_reply and t_first_reply is None:
                t_first_reply = now

            if have_reply and reactions.done:
                # Authoritative: Hermes only sets the terminal reaction after
                # every send for this turn has already completed. This lets us
                # return the instant the turn is really done instead of waiting
                # out the settle window.
                reason = "reaction"
                break
            if have_reply and last_change is not None and (now - last_change) >= self._settle_s:
                # Fallback when reactions aren't available (TELEGRAM_REACTIONS
                # off, or the bot can't react in this chat): the answer has been
                # quiet for settle_s, treat it as done.
                reason = "settle"
                break
            if now >= deadline:
                if have_reply:
                    logger.warning("Reply timeout hit; returning what we have")
                    reason = "timeout"
                    break
                raise TimeoutError(f"No reply from {bot} within {timeout:.0f}s")

            # Adaptive poll cadence: snappy while the turn is fresh (most voice
            # turns finish in a few seconds — this is what the user feels), then
            # back off once a turn is clearly long-running (a tool call) so a
            # multi-minute turn can't rack up enough GetHistoryRequest calls to
            # trip Telegram's flood limit. Fast phase: 0.35s for the first 20s
            # (~57 calls max). Slow phase: 1.5s thereafter.
            elapsed = now - t_send
            await asyncio.sleep(0.35 if elapsed < 20 else 1.5)

        reply = assemble_reply(collected, self._reply_mode)
        n = sum(1 for v in collected.values() if v.strip())
        t_ret = loop.time()
        think = (t_first_reply - t_send) if t_first_reply else (t_ret - t_send)
        overhead = (t_ret - t_first_reply) if t_first_reply else 0.0
        logger.info(
            "Reply from %s: %d msg(s) | think=%.1fs detect_overhead=%.1fs total=%.1fs via=%s",
            bot, n, think, overhead, t_ret - t_send, reason,
        )
        return reply
