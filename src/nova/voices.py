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
# ---- new batch ----
_TERMINATOR = "asetrate=24000*0.85,atempo=1.176,aresample=24000,highpass=f=65,lowpass=f=7000,acompressor=threshold=-14dB:ratio=4,volume=2.5"
_JARVIS = "highpass=f=90,lowpass=f=9500,acompressor=threshold=-20dB:ratio=2,aecho=0.8:0.7:18:0.06"
_EDI = "highpass=f=200,lowpass=f=8000,chorus=0.4:0.8:40:0.25:0.2:1.5,acompressor=threshold=-18dB:ratio=2.5"
_CORTANA = "chorus=0.6:0.9:35|45|55:0.35|0.3|0.28:0.3|0.25|0.4:1.8|1.3|2.1,highpass=f=150,volume=1.6"
_TURRET = "asetrate=24000*1.06,atempo=0.943,aresample=24000,highpass=f=250,lowpass=f=7500,acompressor=threshold=-16dB:ratio=2.5"
_DECTALK = "acrusher=bits=6:mode=log:mix=0.85,highpass=f=200,lowpass=f=4200,volume=3.5,alimiter=limit=0.95"
_C3PO = "highpass=f=220,lowpass=f=7200,acompressor=threshold=-18dB:ratio=2,volume=1.5"
_STATION = "highpass=f=110,lowpass=f=8500,aecho=0.85:0.85:120:0.25,acompressor=threshold=-18dB:ratio=2"
_PA_ANNOUNCE = "highpass=f=280,lowpass=f=3200,aecho=0.7:0.6:70:0.35,acompressor=threshold=-16dB:ratio=4,volume=3"
_ALIEN = "asetrate=24000*0.80,atempo=1.25,aresample=24000,tremolo=f=12:d=0.5,chorus=0.5:0.9:45:0.4:0.3:1.5,highpass=f=60"
_ROBOCOP = "asetrate=24000*0.90,atempo=1.111,aresample=24000,highpass=f=200,lowpass=f=4500,acompressor=threshold=-14dB:ratio=5,volume=3"


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
    {"key": "kokoro:am_echo", **_kok("am_echo"), "cat": "Male", "desc": "resonant"},
    {"key": "kokoro:am_puck", **_kok("am_puck"), "cat": "Male", "desc": "playful"},
    {"key": "kokoro:am_santa", **_kok("am_santa"), "cat": "Male", "desc": "jolly/booming"},
    {"key": "kokoro:bm_daniel", **_kok("bm_daniel", "en-gb"), "cat": "Male", "desc": "British, measured"},
    # ---------------- Piper (different engine) ----------------
    {"key": "piper:en_US-ryan-high", "engine": "piper", "voice": "en_US-ryan-high", "cat": "Piper", "desc": "male (current default)"},
    {"key": "piper:en_US-amy-medium", "engine": "piper", "voice": "en_US-amy-medium", "cat": "Piper", "desc": "female US"},
    {"key": "piper:en_GB-jenny_dioco-medium", "engine": "piper", "voice": "en_GB-jenny_dioco-medium", "cat": "Piper", "desc": "female GB"},
    {"key": "piper:en_GB-alba-medium", "engine": "piper", "voice": "en_GB-alba-medium", "cat": "Piper", "desc": "female Scottish"},
    {"key": "piper:en_US-hfc_female-medium", "engine": "piper", "voice": "en_US-hfc_female-medium", "cat": "Piper", "desc": "female US"},
    {"key": "piper:en_US-kristin-medium", "engine": "piper", "voice": "en_US-kristin-medium", "cat": "Piper", "desc": "female US"},
    {"key": "piper:en_US-kathleen-low", "engine": "piper", "voice": "en_US-kathleen-low", "cat": "Piper", "desc": "female US"},
    {"key": "piper:en_US-ljspeech-high", "engine": "piper", "voice": "en_US-ljspeech-high", "cat": "Piper", "desc": "female US, crisp"},
    {"key": "piper:en_GB-cori-high", "engine": "piper", "voice": "en_GB-cori-high", "cat": "Piper", "desc": "female GB"},
    {"key": "piper:en_US-joe-medium", "engine": "piper", "voice": "en_US-joe-medium", "cat": "Piper", "desc": "male US"},
    {"key": "piper:en_US-john-medium", "engine": "piper", "voice": "en_US-john-medium", "cat": "Piper", "desc": "male US"},
    {"key": "piper:en_US-norman-medium", "engine": "piper", "voice": "en_US-norman-medium", "cat": "Piper", "desc": "male US"},
    {"key": "piper:en_US-bryce-medium", "engine": "piper", "voice": "en_US-bryce-medium", "cat": "Piper", "desc": "male US, young"},
    {"key": "piper:en_US-danny-low", "engine": "piper", "voice": "en_US-danny-low", "cat": "Piper", "desc": "male US, young"},
    {"key": "piper:en_US-hfc_male-medium", "engine": "piper", "voice": "en_US-hfc_male-medium", "cat": "Piper", "desc": "male US"},
    {"key": "piper:en_US-lessac-high", "engine": "piper", "voice": "en_US-lessac-high", "cat": "Piper", "desc": "male US, crisp"},
    {"key": "piper:en_US-kusal-medium", "engine": "piper", "voice": "en_US-kusal-medium", "cat": "Piper", "desc": "male US, accented"},
    {"key": "piper:en_US-sam-medium", "engine": "piper", "voice": "en_US-sam-medium", "cat": "Piper", "desc": "male US"},
    {"key": "piper:en_GB-alan-medium", "engine": "piper", "voice": "en_GB-alan-medium", "cat": "Piper", "desc": "male GB"},
    {"key": "piper:en_GB-northern_english_male-medium", "engine": "piper", "voice": "en_GB-northern_english_male-medium", "cat": "Piper", "desc": "male GB, Northern"},
    # ---------------- Real character models (actual trained voice, not an effect) ----------------
    {"key": "real:glados", "engine": "glados", "cat": "Real model", "desc": "GLaDOS — genuine Portal model (Forward Tacotron+HiFiGAN, trained on Ellen McLain). Fast, ~1s."},
    {"key": "real:nms_suit", "engine": "xvasynth", "ckpt": "resources/app/models/other/x_nomansskysuit.pt",
     "cat": "Real model", "desc": "No Man's Sky exosuit AI — genuine xVASynth model. Fast, ~5-7s."},
    {"key": "real:hal9000", "engine": "rvc", "model_pth": "characters/hal9000/hal_rvc.pth",
     "index_path": "characters/hal9000/added_IVF256_Flat_nprobe_1_hal_rvc_v2.index",
     "rvc_base_voice": "am_onyx", "rvc_base_speed": 0.92,
     "cat": "Real model", "desc": "HAL 9000 — genuine RVC v2 model trained on Douglas Rain's film dialogue. SLOW on CPU (~1-6 min/line) — best for occasional use, not fast back-and-forth."},
    # ---------------- Robot / character (effect on a base voice) ----------------
    {"key": "robot:glados_fx", **_kok("bf_emma", "en-gb", effect=_GLADOS), "cat": "Robot", "desc": "GLaDOS-style, effect-only (F) — prefer real:glados"},
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
    {"key": "robot:terminator", **_kok("am_fenrir", effect=_TERMINATOR), "cat": "Robot", "desc": "Terminator-ish (M)"},
    {"key": "robot:jarvis", **_kok("bm_george", "en-gb", effect=_JARVIS), "cat": "Robot", "desc": "JARVIS-ish, smooth British AI (M)"},
    {"key": "robot:edi", **_kok("af_kore", effect=_EDI), "cat": "Robot", "desc": "EDI-ish, clinical ship AI (F)"},
    {"key": "robot:cortana", **_kok("af_sky", effect=_CORTANA), "cat": "Robot", "desc": "Cortana-ish, ethereal AI (F)"},
    {"key": "robot:turret", **_kok("af_bella", effect=_TURRET), "cat": "Robot", "desc": "cheerful turret AI (F)"},
    {"key": "robot:dectalk", **_kok("am_liam", effect=_DECTALK), "cat": "Robot", "desc": "classic 80s computer voice (M)"},
    {"key": "robot:c3po", **_kok("bm_lewis", "en-gb", effect=_C3PO), "cat": "Robot", "desc": "prim protocol droid (M)"},
    {"key": "robot:station", **_kok("af_river", effect=_STATION), "cat": "Robot", "desc": "space-station computer (F)"},
    {"key": "robot:pa_announce", **_kok("am_adam", effect=_PA_ANNOUNCE), "cat": "Robot", "desc": "PA/announcer system (M)"},
    {"key": "robot:alien", **_kok("am_fenrir", effect=_ALIEN), "cat": "Robot", "desc": "alien/distorted (M)"},
    {"key": "robot:robocop", **_kok("am_michael", effect=_ROBOCOP), "cat": "Robot", "desc": "police-scanner cyborg (M)"},
]

BY_KEY = {v["key"]: v for v in VOICES}


def get(key):
    return BY_KEY.get(key)


def categories():
    out = {}
    for v in VOICES:
        out.setdefault(v["cat"], []).append(v)
    return out
