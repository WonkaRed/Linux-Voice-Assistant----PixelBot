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
import re
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


# --- TTS gate: what Hermes posts to Telegram vs. what should be *spoken* -------
# A single Hermes turn posts several messages to the chat: tool-progress bubbles
# ("💻 terminal: …"), iteration/status lines ("⏳ Still working… iteration 6/90"),
# lifecycle notices ("⚠️ Gateway shutting down…", "💾 Self-improvement review: …"),
# and finally the assistant's actual answer. All of it stays in the Telegram
# thread; only the answer should be read aloud. Two signals separate the answer
# from the chatter, strongest first:
#   1. Structural — the Hermes gateway delivers the real answer as a *reply to
#      the user's message* (reply_to == the id we sent). Every progress/status
#      message is standalone (reply_to is None). Verified across live turns.
#   2. Textual — a fallback for turns with no reply-anchor: progress bubbles are
#      entirely "<glyph> tool_name: …" lines; status lines start with a known
#      lifecycle glyph. Used only when no anchored answer is present.
# We also strip any raw <tool_call> XML a model occasionally leaks into its prose.
_STATUS_PREFIXES = ("⏳", "⚠️", "⚠", "💾", "📦", "⟳", "⏱️", "⏱")
_TOOL_LINE_RE = re.compile(r"^\s*[^\w\s\"'([{]{1,4}\s+[a-z][a-z0-9_]{1,40}\s*(?::\s|\.{3}|…|\().*$")
_TOOLCALL_XML_RE = re.compile(r"<tool_call>.*?</tool_call>", re.S | re.I)
_FUNCTION_XML_RE = re.compile(r"<function=[^>]*>.*?(?:</function>|\Z)", re.S | re.I)
_STRAY_TAG_RE = re.compile(r"</?(?:tool_call|function|parameter)(?:=[^>]*)?>", re.I)


def _is_tool_bubble(text: str) -> bool:
    """True if every non-empty line is a Hermes tool-progress line ("💻 terminal: …")."""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return bool(lines) and all(_TOOL_LINE_RE.match(ln) for ln in lines)


def is_agent_noise(text: str) -> bool:
    """True if a message is tool-progress or lifecycle/status chatter, not an answer."""
    s = text.strip()
    if not s:
        return True
    if s.startswith(_STATUS_PREFIXES):
        return True
    return _is_tool_bubble(s)


def sanitize_for_voice(text: str) -> str:
    """Strip tool-call XML a model sometimes leaks inline, then tidy whitespace."""
    text = _TOOLCALL_XML_RE.sub("", text)
    text = _FUNCTION_XML_RE.sub("", text)
    text = _STRAY_TAG_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def assemble_reply(collected: dict, mode: str = "last", anchored_ids=None) -> str:
    """
    Turn the {message_id: text} map gathered from the bot into the string to
    *speak*. Tool-progress, iteration and lifecycle messages are gated out here
    — they stay in the Telegram thread; this only decides what TTS reads.

    Selection, strongest signal first:
      • messages replying to our trigger (``anchored_ids``) — the real answer,
        joined in id order so a long answer split across messages stays whole;
      • else non-noise messages, per ``mode`` (``last`` / ``concat``);
      • else, to never go silent, the last non-empty message as-is.
    """
    ids = sorted(collected)
    nonempty = [i for i in ids if collected[i].strip()]
    if not nonempty:
        return ""

    anchored = [i for i in nonempty
                if anchored_ids and i in anchored_ids and not _is_tool_bubble(collected[i])]
    if anchored:
        text = "\n\n".join(collected[i].strip() for i in anchored)
    else:
        content = [i for i in nonempty if not is_agent_noise(collected[i])]
        if content:
            text = (collected[content[-1]] if mode == "last"
                    else "\n\n".join(collected[i].strip() for i in content)).strip()
        else:
            text = collected[nonempty[-1]].strip()
    return sanitize_for_voice(text)


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
    def _reply_to_id(msg):
        """The message id this message replies to, or None. Handles both the
        legacy ``reply_to_msg_id`` attribute and the newer ``reply_to`` header."""
        rid = getattr(msg, "reply_to_msg_id", None)
        if rid is not None:
            return rid
        header = getattr(msg, "reply_to", None)
        return getattr(header, "reply_to_msg_id", None) if header else None

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
        anchored_ids: set = set()  # ids replying to our trigger = the real answer
        last_change: Optional[float] = None
        reactions = ReactionTracker()
        t_first_reply: Optional[float] = None   # when the real answer first landed
        reason = "?"

        def answer_present() -> bool:
            # A real, speakable answer exists — an anchored reply, or (fallback)
            # any non-noise message. Tool bubbles / status lines don't count, so
            # the settle window can't fire on a transient "💻 terminal: …" bubble.
            for i, body in collected.items():
                if not body.strip():
                    continue
                if i in anchored_ids and not _is_tool_bubble(body):
                    return True
            return any(v.strip() and not is_agent_noise(v) for v in collected.values())

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
                if self._reply_to_id(msg) == baseline:
                    anchored_ids.add(msg.id)

            now = loop.time()
            have_any = any(v.strip() for v in collected.values())
            have_answer = answer_present()
            if have_answer and t_first_reply is None:
                t_first_reply = now

            if have_any and reactions.done:
                # Authoritative: Hermes only sets the terminal reaction after
                # every send for this turn has already completed. This lets us
                # return the instant the turn is really done instead of waiting
                # out the settle window.
                reason = "reaction"
                break
            if have_answer and last_change is not None and (now - last_change) >= self._settle_s:
                # Fallback when reactions aren't available (TELEGRAM_REACTIONS
                # off, or the bot can't react in this chat): the *answer* (not a
                # tool bubble) has been quiet for settle_s, treat it as done.
                reason = "settle"
                break
            if now >= deadline:
                if have_any:
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

        reply = assemble_reply(collected, self._reply_mode, anchored_ids)
        n = sum(1 for v in collected.values() if v.strip())
        n_gated = n - sum(1 for i, v in collected.items()
                          if v.strip() and (i in anchored_ids or not is_agent_noise(v)))
        t_ret = loop.time()
        think = (t_first_reply - t_send) if t_first_reply else (t_ret - t_send)
        overhead = (t_ret - t_first_reply) if t_first_reply else 0.0
        logger.info(
            "Reply from %s: %d msg(s), %d gated from TTS | think=%.1fs detect_overhead=%.1fs total=%.1fs via=%s",
            bot, n, n_gated, think, overhead, t_ret - t_send, reason,
        )
        return reply
