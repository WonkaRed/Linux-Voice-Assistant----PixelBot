"""
Unified TTS synthesis across engines (Kokoro, Piper) with optional ffmpeg
effect chains. Used by both the runtime voice and the `nova tts-model` picker,
so a preview sounds exactly like what you'll get in use.
"""
import os
import subprocess
import wave

import numpy as np

_MODELS = os.path.expanduser("~/.nova/models")
_kokoro = None
_piper_cache = {}


def _kokoro_inst():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(
            os.path.join(_MODELS, "kokoro", "kokoro-v1.0.onnx"),
            os.path.join(_MODELS, "kokoro", "voices-v1.0.bin"),
        )
    return _kokoro


def _piper_voice(name):
    if name not in _piper_cache:
        from piper import PiperVoice
        _piper_cache[name] = PiperVoice.load(os.path.join(_MODELS, "piper", f"{name}.onnx"))
    return _piper_cache[name]


def _write_wav(path, pcm_int16_bytes, sample_rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_int16_bytes)


def synth_to_wav(entry: dict, text: str, out_path: str) -> str:
    """Render ``text`` in the voice described by ``entry`` to ``out_path``."""
    engine = entry["engine"]
    tmp = out_path + ".dry.wav"

    if engine == "kokoro":
        samples, sr = _kokoro_inst().create(
            text, voice=entry["voice"], speed=entry.get("speed", 1.0),
            lang=entry.get("lang", "en-us"),
        )
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        _write_wav(tmp, pcm, sr)
    elif engine == "piper":
        voice = _piper_voice(entry["voice"])
        pcm = b"".join(c.audio_int16_bytes for c in voice.synthesize(text))
        _write_wav(tmp, pcm, voice.config.sample_rate)
    else:
        raise ValueError(f"unknown TTS engine: {engine}")

    effect = entry.get("effect")
    if effect:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", tmp, "-af", effect, out_path],
            check=True, timeout=30,
        )
        try:
            os.remove(tmp)
        except OSError:
            pass
    else:
        os.replace(tmp, out_path)
    return out_path
