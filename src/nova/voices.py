"""
Voice catalog for Nova's TTS — the set the `nova tts-model` picker offers and
that the running bridge speaks with. Each entry is self-contained: engine +
model/voice reference. The `key` is what gets written to config
(agents.<name>.voice) and used as the preview-cache filename.

Trimmed to what's actually in use (2026-07-03 housekeeping): three genuine
trained character models, plus the one Piper voice main.py hardcodes as its
safety-net fallback. The earlier 70-voice catalog (Kokoro/Piper naturals +
ffmpeg-effect robot approximations) was removed — none of it was selected
once real trained models were available; see git history to bring any of it
back if wanted.
"""

VOICES = [
    {"key": "real:glados", "engine": "glados", "cat": "Real model",
     "desc": "GLaDOS — genuine Portal model (Forward Tacotron+HiFiGAN, trained on Ellen McLain). CPU, ~1s."},
    {"key": "real:cyclops", "engine": "rvc", "model_pth": "characters/cyclops/cyclops_500e_3000s.pth",
     "index_path": "characters/cyclops/cyclops.index",
     "rvc_base_voice": "am_onyx", "rvc_base_speed": 0.95,
     "cat": "Real model", "desc": "Subnautica Cyclops AI — genuine RVC v2 model (500 epochs). CPU, ~2-4s via persistent server."},
    {"key": "real:hal9000", "engine": "rvc", "model_pth": "characters/hal9000/hal_rvc.pth",
     "index_path": "characters/hal9000/added_IVF256_Flat_nprobe_1_hal_rvc_v2.index",
     "rvc_base_voice": "am_onyx", "rvc_base_speed": 0.92,
     "cat": "Real model", "desc": "HAL 9000 — genuine RVC v2 model trained on Douglas Rain's film dialogue. CPU, ~2-4s via persistent server."},
    # Safety-net fallback: used when an agent has no configured voice, or its
    # configured key doesn't resolve (see main.py's _load_models).
    {"key": "piper:en_US-ryan-high", "engine": "piper", "voice": "en_US-ryan-high",
     "cat": "Fallback", "desc": "plain natural male voice — used if a real-model voice fails to load"},
]

BY_KEY = {v["key"]: v for v in VOICES}


def get(key):
    return BY_KEY.get(key)


def categories():
    out = {}
    for v in VOICES:
        out.setdefault(v["cat"], []).append(v)
    return out
