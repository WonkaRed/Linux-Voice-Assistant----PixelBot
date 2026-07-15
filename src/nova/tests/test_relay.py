import pytest

from nova.relay import (
    assemble_reply,
    is_agent_noise,
    sanitize_for_voice,
    ReactionTracker,
    TelegramRelay,
)


def test_assemble_last_picks_final_message():
    collected = {10: "thinking…", 11: "Here is the answer."}
    assert assemble_reply(collected, "last") == "Here is the answer."


def test_assemble_last_ignores_trailing_empty():
    # Empty/whitespace messages (e.g. a cleared status line) are skipped.
    collected = {10: "The answer.", 11: "   "}
    assert assemble_reply(collected, "last") == "The answer."


def test_assemble_concat_joins_in_id_order():
    collected = {12: "second", 10: "first"}
    assert assemble_reply(collected, "concat") == "first\n\nsecond"


def test_assemble_empty():
    assert assemble_reply({}, "last") == ""
    assert assemble_reply({5: "  "}, "concat") == ""


def test_reply_mode_validated():
    with pytest.raises(ValueError):
        TelegramRelay(api_id=1, api_hash="x", session="/tmp/x.session", reply_mode="bogus")


# ---------------------------------------------------------------- TTS gate
# Real message shapes captured from a live @JailbrokenAgentBot turn.
TOOL_BUBBLE = '💻 terminal: "hostname && ps aux --sort=-%mem | hea..."'
SKILL_BUBBLE = '📚 skill_view: "substance-prep"'
ITERATION = "⏳ Still working... (9 min elapsed — iteration 6/90, waiting for provider response (streaming))"
GW_WARNING = "⚠️ Gateway shutting down — Your current task will be interrupted."
SELF_IMPROVE = "💾 Self-improvement review: Skill 'music-search-download' created."
ANSWER = "I'm on pop-os (this desktop), and the top two memory hogs are Nova dictation daemon at 2.8 GB and the RVC server at 2.6 GB."


def test_is_agent_noise_classifies_hermes_chatter():
    assert is_agent_noise(TOOL_BUBBLE)
    assert is_agent_noise(SKILL_BUBBLE)
    assert is_agent_noise(ITERATION)
    assert is_agent_noise(GW_WARNING)
    assert is_agent_noise(SELF_IMPROVE)
    assert is_agent_noise("💻 terminal...")           # no-preview variant
    assert is_agent_noise("")                          # empty
    # A multi-line progress bubble is entirely tool lines.
    assert is_agent_noise(f"{TOOL_BUBBLE}\n{SKILL_BUBBLE}")


def test_is_agent_noise_keeps_real_answers():
    assert not is_agent_noise(ANSWER)
    assert not is_agent_noise("See you later, bro.")
    # Prose that merely starts with an emoji is not a tool line.
    assert not is_agent_noise("✅ Done — freed 2 GB of RAM by killing the leaked worker.")


def test_gate_prefers_anchored_answer_over_tool_and_status():
    # baseline=100 (our message); the answer replies to it, chatter doesn't.
    collected = {101: TOOL_BUBBLE, 102: ITERATION, 103: ANSWER, 104: GW_WARNING}
    assert assemble_reply(collected, "last", anchored_ids={103}) == ANSWER


def test_gate_joins_split_anchored_answer():
    collected = {101: TOOL_BUBBLE, 102: "First half.", 103: "Second half."}
    assert assemble_reply(collected, "last", anchored_ids={102, 103}) == "First half.\n\nSecond half."


def test_gate_fallback_strips_noise_when_no_anchor():
    # No reply-anchor available (e.g. TELEGRAM_REACTIONS off, older gateway).
    collected = {101: TOOL_BUBBLE, 102: ITERATION, 103: ANSWER}
    assert assemble_reply(collected, "last") == ANSWER


def test_gate_never_goes_silent_on_all_noise():
    # Pathological: only chatter arrived — speak the last thing rather than nothing.
    collected = {101: TOOL_BUBBLE, 102: ITERATION}
    assert assemble_reply(collected, "last") == ITERATION


def test_gate_drops_anchored_tool_bubble():
    # Defense-in-depth: even if a tool bubble were reply-anchored, it's not spoken.
    collected = {101: TOOL_BUBBLE, 102: ANSWER}
    assert assemble_reply(collected, "last", anchored_ids={101, 102}) == ANSWER


def test_gate_anchored_pure_xml_falls_back_to_content():
    # An anchored message that is only tool-call XML sanitizes to empty — the
    # gate must fall through to real content rather than going silent.
    xml_only = "<tool_call>\n<function=terminal>\n</function>\n</tool_call>"
    collected = {50: xml_only, 51: "The real answer."}
    assert assemble_reply(collected, "last", anchored_ids={50}) == "The real answer."


def test_gate_never_silent_even_if_everything_sanitizes_empty():
    xml_only = "<tool_call></tool_call>"
    # Only message is empty-after-sanitize → returns it raw rather than "".
    assert assemble_reply({50: xml_only}, "last", anchored_ids={50}) == xml_only


def test_sanitize_strips_leaked_tool_call_xml():
    leaked = (
        "Alright bro, let me just grab that full track!\n\n"
        "<tool_call>\n<function=terminal>\n<parameter=command>\n"
        'curl -s "https://example/api"\n</parameter>\n</function>\n</tool_call>'
    )
    assert sanitize_for_voice(leaked) == "Alright bro, let me just grab that full track!"
    # Applied through the gate on an anchored answer too.
    assert assemble_reply({50: leaked}, "last", anchored_ids={50}) == (
        "Alright bro, let me just grab that full track!"
    )


# ---------------------------------------------------------------------- ReactionTracker

def test_reaction_tracker_terminal_marks_done():
    t = ReactionTracker()
    assert t.update({"\U0001f440"}) is False   # in progress (eyes)
    assert t.update({"\U0001f440"}) is False   # still working, e.g. a slow tool call
    assert t.update({"\U0001f44d"}) is True    # thumbs up => success, done
    # Latches: even if a later poll (race/glitch) sees something else.
    assert t.update(set()) is True


def test_reaction_tracker_thumbs_down_is_also_terminal():
    t = ReactionTracker()
    t.update({"\U0001f440"})
    assert t.update({"\U0001f44e"}) is True


def test_reaction_tracker_cleared_after_in_progress_is_cancelled_done():
    t = ReactionTracker()
    t.update({"\U0001f440"})
    assert t.update(set()) is True  # reaction cleared => Hermes cancelled the turn


def test_reaction_tracker_never_seen_stays_not_done():
    # No TELEGRAM_REACTIONS on the gateway (or the bot can't react in this
    # chat) => no reaction ever appears => pure fallback to settle_s, forever.
    t = ReactionTracker()
    for _ in range(5):
        assert t.update(set()) is False


def test_reaction_tracker_empty_before_in_progress_is_not_done():
    # A poll can land before Hermes has set the in-progress reaction yet.
    t = ReactionTracker()
    assert t.update(set()) is False
    assert t.update({"\U0001f440"}) is False


# ---------------------------------------------------------------------- reaction extraction

class _FakeEmoji:
    def __init__(self, emoticon):
        self.emoticon = emoticon


class _FakeReactionCount:
    def __init__(self, emoticon):
        self.reaction = _FakeEmoji(emoticon)


class _FakeReactions:
    def __init__(self, results):
        self.results = results


class _FakeMessage:
    def __init__(self, reactions=None):
        self.reactions = reactions


def test_reaction_emojis_of_no_reactions_field():
    assert TelegramRelay._reaction_emojis_of(_FakeMessage(reactions=None)) == set()


def test_reaction_emojis_of_empty_results():
    assert TelegramRelay._reaction_emojis_of(_FakeMessage(reactions=_FakeReactions([]))) == set()


def test_reaction_emojis_of_extracts_emoticons():
    msg = _FakeMessage(reactions=_FakeReactions([
        _FakeReactionCount("\U0001f440"),
        _FakeReactionCount("\U0001f44d"),
    ]))
    assert TelegramRelay._reaction_emojis_of(msg) == {"\U0001f440", "\U0001f44d"}
