import pytest

from nova.relay import assemble_reply, TelegramRelay


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
