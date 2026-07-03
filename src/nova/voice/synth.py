"""
Unified TTS synthesis across engines (Kokoro, Piper) with optional ffmpeg
effect chains. Used by both the runtime voice and the `nova tts-model` picker,
so a preview sounds exactly like what you'll get in use.
"""
import json
import os
import socket
import subprocess
import time
import wave

import numpy as np

_MODELS = os.path.expanduser("~/.nova/models")
_GLADOS_DIR = os.path.expanduser("~/.nova/glados")
_RVC_DIR = os.path.expanduser("~/.nova/rvc")
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


_RVC_SOCK = "/tmp/nova-rvc.sock"


def _rvc_ping(timeout=1.0) -> bool:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(_RVC_SOCK)
        s.sendall(b'{"ping": true}\n')
        resp = json.loads(s.makefile().readline())
        s.close()
        return bool(resp.get("ok"))
    except Exception:
        return False


def _rvc_ensure_running(startup_timeout=90.0) -> None:
    if _rvc_ping():
        return
    subprocess.Popen(
        [os.path.join(_RVC_DIR, "venv", "bin", "python"), os.path.join(_RVC_DIR, "rvc_server.py")],
        cwd=_RVC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + startup_timeout
    while time.time() < deadline:
        if _rvc_ping():
            return
        time.sleep(1.0)
    raise RuntimeError(f"RVC server did not come up within {startup_timeout:.0f}s")


def _rvc_request(req: dict, timeout=120.0) -> None:
    _rvc_ensure_running()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(_RVC_SOCK)
    s.sendall((json.dumps(req) + "\n").encode("utf-8"))
    resp = json.loads(s.makefile().readline())
    s.close()
    if not resp.get("ok"):
        raise RuntimeError(f"RVC synth failed: {resp.get('error')}")


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
    elif engine == "glados":
        # Real trained GLaDOS model (Forward Tacotron + HiFiGAN) — an isolated
        # venv/subprocess because it needs deep-phonemizer/pydub/nltk that we
        # don't want bleeding into Nova's main environment.
        subprocess.run(
            [os.path.join(_GLADOS_DIR, ".venv", "bin", "python"),
             os.path.join(_GLADOS_DIR, "glados_synth.py"), text, tmp],
            check=True, timeout=60, cwd=_GLADOS_DIR,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif engine == "rvc":
        # TTS (Kokoro) -> RVC v2 voice conversion to a trained character
        # timbre, via a persistent CPU-only server (hubert+rmvpe+model stay
        # loaded in RAM) so replies come back in a few seconds instead of
        # reloading ~200MB of weights on every call. Auto-starts the server
        # if it isn't running. CPU only — never touches the GPU.
        _rvc_request({
            "text": text,
            "model_pth": entry["model_pth"],
            "index_path": entry["index_path"],
            "out_path": tmp,
            "base_voice": entry.get("rvc_base_voice", "am_onyx"),
            "base_speed": entry.get("rvc_base_speed", 0.92),
        })
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
