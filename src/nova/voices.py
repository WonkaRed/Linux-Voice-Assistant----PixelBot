"""
Voice catalog for Nova's TTS — the set the `nova tts-model` picker offers and
that the running bridge speaks with. Each entry is self-contained: engine +
voice id (+ optional speed and ffmpeg effect chain). The `key` is what gets
written to config (voice.selection) and used as the preview-cache filename.
"""

# --- robot effect chains (ffmpeg -af), applied on top of a base neural voice ---
_GLADOS = "highpass=f=180,lowpass=f=6800,flanger=depth=2:speed=0.28,acompressor=threshold=-18dB:ratio=3,volume=2"
_DALEK = "tremolo=f=32:d=0.85,highpass=f=120,lowpass=f=6000,acompressor=threshold=-16dB:ratio=4,volume=3,alimiter=limit=0.95"
_RETRO = "acrusher=bits=7:mode=log:mix=0.7,highpass=f=250,lowpass=f=3800,volume=3,alimiter=limit=0.95"
_VOCODER = "chorus=0.5:0.9:50|60:0.4|0.32:0.25|0.4:2|1.3,highpass=f=110"
_HAL = "acompressor=threshold=-16dB:ratio=2.5,highpass=f=70,lowpass=f=8500,aecho=0.9:0.9:55:0.12"
_TARS = "asetrate=24000*0.92,atempo=1.087,aresample=24000,highpass=f=80,lowpass=f=8000,acompressor=threshold=-18dB:ratio=3"
_CYLON = "flanger=depth=3:speed=0.4,tremolo=f=18:d=0.35,highpass=f=100"
_DEEPROBOT = "asetrate=24000*0.88,atempo=1.136,aresample=24000,flanger=depth=3:speed=0.5,highpass=f=90"
_COMMS = "highpass=f=300,lowpass=f=3400,acompressor=threshold=-18dB:ratio=4,volume=3.5,alimiter=limit=0.95"
_PDA = "highpass=f=100,lowpass=f=9000,acompressor=threshold=-18dB:ratio=2.5,aecho=0.85:0.9:26:0.08"


def _kok(voice, lang="en-us", **kw):
    return {"engine": "kokoro", "voice": voice, "lang": lang, **kw}


VOICES = [
    # ---------------- Kokoro female (US) ----------------
    {"key": "kokoro:af_heart", **_kok("af_heart"), "cat": "Female · US", "desc": "warm, friendly"},
    {"key": "kokoro:af_bella", **_kok("af_bella"), "cat": "Female · US", "desc": "bright"},
    {"key": "kokoro:af_nicole", **_kok("af_nicole"), "cat": "Female · US", "desc": "soft/breathy"},
    {"key": "kokoro:af_sarah", **_kok("af_sarah"), "cat": "Female · US", "desc": "clear"},
    {"key": "kokoro:af_aoede", **_kok("af_aoede"), "cat": "Female · US", "desc": "smooth"},
    {"key": "kokoro:af_kore", **_kok("af_kore"), "cat": "Female · US", "desc": "even"},
    {"key": "kokoro:af_sky", **_kok("af_sky"), "cat": "Female · US", "desc": "light"},
    {"key": "kokoro:af_jessica", **_kok("af_jessica"), "cat": "Female · US", "desc": "natural"},
    {"key": "kokoro:af_river", **_kok("af_river"), "cat": "Female · US", "desc": "calm, flat, assistant-y"},
    {"key": "kokoro:af_nova", **_kok("af_nova"), "cat": "Female · US", "desc": "crisp"},
    {"key": "kokoro:af_alloy", **_kok("af_alloy"), "cat": "Female · US", "desc": "neutral"},
    # ---------------- Kokoro female (GB) ----------------
    {"key": "kokoro:bf_emma", **_kok("bf_emma", "en-gb"), "cat": "Female · UK", "desc": "calm British (PDA-ish)"},
    {"key": "kokoro:bf_alice", **_kok("bf_alice", "en-gb"), "cat": "Female · UK", "desc": "clear British"},
    {"key": "kokoro:bf_isabella", **_kok("bf_isabella", "en-gb"), "cat": "Female · UK", "desc": "warm British"},
    {"key": "kokoro:bf_lily", **_kok("bf_lily", "en-gb"), "cat": "Female · UK", "desc": "soft British"},
    # ---------------- Kokoro male ----------------
    {"key": "kokoro:am_onyx", **_kok("am_onyx"), "cat": "Male", "desc": "deepest, authoritative"},
    {"key": "kokoro:am_michael", **_kok("am_michael"), "cat": "Male", "desc": "deep"},
    {"key": "kokoro:am_adam", **_kok("am_adam"), "cat": "Male", "desc": "natural"},
    {"key": "kokoro:am_eric", **_kok("am_eric"), "cat": "Male", "desc": "clear"},
    {"key": "kokoro:am_liam", **_kok("am_liam"), "cat": "Male", "desc": "even"},
    {"key": "kokoro:am_fenrir", **_kok("am_fenrir"), "cat": "Male", "desc": "gruff"},
    {"key": "kokoro:bm_george", **_kok("bm_george", "en-gb"), "cat": "Male", "desc": "British"},
    {"key": "kokoro:bm_lewis", **_kok("bm_lewis", "en-gb"), "cat": "Male", "desc": "British, deep"},
    {"key": "kokoro:bm_fable", **_kok("bm_fable", "en-gb"), "cat": "Male", "desc": "British, storyteller"},
    # ---------------- Piper (different engine) ----------------
    {"key": "piper:en_US-ryan-high", "engine": "piper", "voice": "en_US-ryan-high", "cat": "Piper", "desc": "male (current default)"},
    {"key": "piper:en_US-amy-medium", "engine": "piper", "voice": "en_US-amy-medium", "cat": "Piper", "desc": "female US"},
    {"key": "piper:en_GB-jenny_dioco-medium", "engine": "piper", "voice": "en_GB-jenny_dioco-medium", "cat": "Piper", "desc": "female GB"},
    {"key": "piper:en_GB-alba-medium", "engine": "piper", "voice": "en_GB-alba-medium", "cat": "Piper", "desc": "female Scottish"},
    {"key": "piper:en_US-hfc_female-medium", "engine": "piper", "voice": "en_US-hfc_female-medium", "cat": "Piper", "desc": "female US"},
    {"key": "piper:en_US-kristin-medium", "engine": "piper", "voice": "en_US-kristin-medium", "cat": "Piper", "desc": "female US"},
    # ---------------- Robot / character (effect on a base voice) ----------------
    {"key": "robot:glados", **_kok("bf_emma", "en-gb", effect=_GLADOS), "cat": "Robot", "desc": "GLaDOS-style (F)"},
    {"key": "robot:pda_emma", **_kok("bf_emma", "en-gb", effect=_PDA), "cat": "Robot", "desc": "Subnautica-PDA-style (F)"},
    {"key": "robot:pda_alice", **_kok("bf_alice", "en-gb", effect=_PDA), "cat": "Robot", "desc": "PDA-style, clearer (F)"},
    {"key": "robot:comms_ai", **_kok("af_nicole", effect=_COMMS), "cat": "Robot", "desc": "radio/comms AI (F)"},
    {"key": "robot:vocoder", **_kok("af_alloy", effect=_VOCODER), "cat": "Robot", "desc": "vocoder AI (F)"},
    {"key": "robot:retro", **_kok("af_alloy", effect=_RETRO), "cat": "Robot", "desc": "retro computer (F)"},
    {"key": "robot:dalek", **_kok("am_onyx", effect=_DALEK), "cat": "Robot", "desc": "Dalek buzz (M)"},
    {"key": "robot:hal9000", **_kok("am_onyx", speed=0.82, effect=_HAL), "cat": "Robot", "desc": "HAL 9000 (M)"},
    {"key": "robot:tars", **_kok("am_onyx", effect=_TARS), "cat": "Robot", "desc": "TARS-ish deep (M)"},
    {"key": "robot:cylon", **_kok("am_michael", effect=_CYLON), "cat": "Robot", "desc": "Cylon metallic (M)"},
    {"key": "robot:deep_robot", **_kok("am_michael", effect=_DEEPROBOT), "cat": "Robot", "desc": "deep robot (M)"},
]

BY_KEY = {v["key"]: v for v in VOICES}


def get(key):
    return BY_KEY.get(key)


def categories():
    out = {}
    for v in VOICES:
        out.setdefault(v["cat"], []).append(v)
    return out
