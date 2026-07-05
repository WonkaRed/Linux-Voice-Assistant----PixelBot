"""Anti-echo speech-queue behaviour: TTS must never play while recording."""
import time

from nova.config import Config
from nova.main import VoiceBridge


class FakeTTS:
    def __init__(self):
        self.spoken = []
        self._speaking = False

    def speak(self, text, blocking=True, should_continue=None):
        # Honour the barge-in gate like the real engine: if the turn was
        # invalidated before we start, don't "play".
        if should_continue is not None and not should_continue():
            return True
        self._speaking = True
        self.spoken.append(text)
        self._speaking = False
        return True

    def stop(self):
        self._speaking = False

    def is_speaking(self):
        return self._speaking


def _bridge():
    b = VoiceBridge(Config.load())
    b.tts_engines = {"pixelbot": FakeTTS(), "jailbreak": FakeTTS()}
    b._running = True
    b._start_speech_worker()
    return b


def test_speech_plays_when_idle():
    b = _bridge()
    b._speak("pixelbot", "hello world")
    time.sleep(0.4)
    assert b.tts_engines["pixelbot"].spoken == ["hello world"]
    b._running = False


def test_speech_held_while_recording_then_plays():
    b = _bridge()
    b._rec_active.set()          # pretend the mic is live
    b._speak("pixelbot", "delayed reply")
    time.sleep(0.4)
    assert b.tts_engines["pixelbot"].spoken == []     # must NOT play during recording (would echo)
    b._rec_active.clear()         # recording stopped
    time.sleep(0.4)
    assert b.tts_engines["pixelbot"].spoken == ["delayed reply"]
    b._running = False


def test_flush_drops_queued_and_stops_playback():
    b = _bridge()
    b._rec_active.set()
    b._speak("pixelbot", "stale one")
    b._speak("pixelbot", "stale two")
    time.sleep(0.2)
    b._flush_speech()             # barge-in
    b._rec_active.clear()
    time.sleep(0.4)
    assert b.tts_engines["pixelbot"].spoken == []     # both dropped
    b._running = False


def test_each_agent_speaks_in_its_own_voice():
    b = _bridge()
    b._speak("pixelbot", "nms line")
    b._speak("jailbreak", "hal line")
    time.sleep(0.5)
    assert b.tts_engines["pixelbot"].spoken == ["nms line"]
    assert b.tts_engines["jailbreak"].spoken == ["hal line"]
    b._running = False
