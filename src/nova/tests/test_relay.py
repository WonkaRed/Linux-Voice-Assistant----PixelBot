import pytest

from nova.relay import assemble_reply, ReactionTracker, TelegramRelay


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
