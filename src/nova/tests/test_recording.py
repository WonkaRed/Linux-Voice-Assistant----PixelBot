"""Push-to-talk state machine + steer/queue command prefix.

The toggle logic is tested in isolation by stubbing the two effectful methods
(_start_listening / _stop_and_process) so we assert the *decisions* without
touching real audio/STT.
"""
from nova.config import Config
from nova.main import VoiceBridge, _RecSession


def _bridge():
    b = VoiceBridge(Config.load())
    b._running = True
    b._debounce_s = 0.0  # exercise transition logic without wall-clock debounce
    calls = []

    def fake_start(agent):
        calls.append(("start", agent))
        b._session = _RecSession(agent, None, None)

    def fake_stop():
        calls.append(("stop", b._session.agent if b._session else None))
        b._session = None

    b._start_listening = fake_start
    b._stop_and_process = fake_stop
    b.calls = calls
    return b


# ---------------------------------------------------------------- state machine

def test_idle_press_starts_recording():
    b = _bridge()
    b._toggle("pixelbot")
    assert b.calls == [("start", "pixelbot")]


def test_same_key_stops_and_sends():
    b = _bridge()
    b._toggle("pixelbot")
    b._toggle("pixelbot")
    assert b.calls == [("start", "pixelbot"), ("stop", "pixelbot")]


def test_different_agent_sends_current_then_records_new():
    # The core fix: F4 (record pixelbot) then F8 must send to pixelbot ONLY and
    # immediately start recording jailbreak — never send the same words to both.
    b = _bridge()
    b._toggle("pixelbot")
    b._toggle("jailbreak")
    assert b.calls == [("start", "pixelbot"), ("stop", "pixelbot"), ("start", "jailbreak")]


def test_stop_command_sends_current():
    b = _bridge()
    b._toggle("pixelbot")
    b._toggle("__stop__")
    assert b.calls == [("start", "pixelbot"), ("stop", "pixelbot")]


def test_stop_command_when_idle_is_noop():
    b = _bridge()
    b._toggle("__stop__")
    assert b.calls == []


def test_switch_is_never_debounced():
    # Even back-to-back, a real agent switch must go through (only same-key/idle
    # presses are debounced).
    b = _bridge()
    b._debounce_s = 999  # would swallow a same-key repeat…
    b._toggle("pixelbot")
    b._toggle("jailbreak")  # …but a switch must not be swallowed
    assert b.calls == [("start", "pixelbot"), ("stop", "pixelbot"), ("start", "jailbreak")]


def test_same_key_repeat_is_debounced():
    b = _bridge()
    b._debounce_s = 999
    b._toggle("pixelbot")
    b._toggle("pixelbot")   # within debounce window → ignored
    assert b.calls == [("start", "pixelbot")]


# ---------------------------------------------------------------- steer / queue

def test_steer_prefix():
    b = VoiceBridge(Config.load())
    assert b._apply_command_prefix("steer focus on the database") == "/steer focus on the database"


def test_queue_prefix():
    b = VoiceBridge(Config.load())
    assert b._apply_command_prefix("queue remind me later") == "/queue remind me later"


def test_prefix_is_case_insensitive_and_eats_punctuation():
    b = VoiceBridge(Config.load())
    assert b._apply_command_prefix("Steer, do the thing") == "/steer do the thing"
    assert b._apply_command_prefix("Queue: check the logs") == "/queue check the logs"


def test_prefix_does_not_trigger_mid_word():
    b = VoiceBridge(Config.load())
    # "steering" / "queuer" must NOT be treated as commands.
    assert b._apply_command_prefix("steering the project carefully") == "steering the project carefully"


def test_bare_command_word():
    b = VoiceBridge(Config.load())
    assert b._apply_command_prefix("steer") == "/steer"


def test_normal_message_untouched():
    b = VoiceBridge(Config.load())
    assert b._apply_command_prefix("what's the weather today") == "what's the weather today"
