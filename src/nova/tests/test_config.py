import textwrap

import pytest

from nova.config import Config, DEFAULTS, telegram_credentials


def test_defaults_when_no_file(tmp_path):
    cfg = Config.load(tmp_path / "does-not-exist.yaml")
    assert cfg.get("voice.stt_model") == "large-v3"
    assert cfg.agent_names == ["pixelbot", "jailbreak"]
    assert cfg.get("relay.settle_s") == 2.5


def test_user_file_deep_merges(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent("""
        voice:
          stt_model: medium.en
        agents:
          pixelbot:
            reply_timeout_s: 42
    """))
    cfg = Config.load(p)
    # Overridden leaf:
    assert cfg.get("voice.stt_model") == "medium.en"
    assert cfg.agent("pixelbot")["reply_timeout_s"] == 42
    # Untouched sibling keys survive the merge:
    assert cfg.agent("pixelbot")["bot"] == DEFAULTS["agents"]["pixelbot"]["bot"]
    assert cfg.agent("jailbreak")["bot"] == "@JailbreakBot"


def test_agent_unknown_raises(tmp_path):
    cfg = Config.load(tmp_path / "none.yaml")
    with pytest.raises(KeyError):
        cfg.agent("nope")


def test_expanduser(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    cfg = Config.load(tmp_path / "none.yaml")
    p = cfg.expanduser("voice.tts_voice")
    assert p and not p.startswith("~")


def test_telegram_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    with pytest.raises(RuntimeError):
        telegram_credentials()

    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc")
    assert telegram_credentials() == (12345, "abc")

    monkeypatch.setenv("TELEGRAM_API_ID", "not-an-int")
    with pytest.raises(RuntimeError):
        telegram_credentials()
