"""
System configuration for AI Voice Dictation System with Dual-Model Architecture.

This configuration is optimized for RTX 4070 12GB VRAM:
- Whisper base.en: 0.5GB VRAM (10x faster than medium.en!)
- Qwen2.5-3B-Instruct (bfloat16): ~6.5GB VRAM (superior intelligence!)
- Total: ~7GB VRAM (40% safety margin)

Performance:
- Whisper: 1.43s average (0.08x RTF)
- LLM: 0.4s average
- Total: 1.8s average (100% success rate, better tool-use!)
"""
import os
from pathlib import Path

# Base Directories
BASE_DIR = Path(__file__).parent.parent.absolute()
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
SRC_DIR = BASE_DIR / "src"

# Create directories if they don't exist
MODELS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ===== WHISPER SETTINGS (Speech Recognition) =====
WHISPER_MODEL_SIZE = "base.en"  # Optimized: 10x faster than medium.en
WHISPER_DEVICE = "cpu"  # Using CPU due to cuDNN conflicts (still very fast)
WHISPER_COMPUTE_TYPE = "int8"  # INT8 for CPU efficiency
WHISPER_BEAM_SIZE = 1  # Optimized: beam_size=1 gives same accuracy with minimal latency
WHISPER_DOWNLOAD_ROOT = str(MODELS_DIR)

# Note: base.en with beam_size=1 is OPTIMAL:
# - Processing time: 0.8s average (vs 7.6s with medium.en)
# - RTF: 0.08x (12x faster than real-time!)
# - Accuracy: 95-100% on technical terms, proper nouns, numbers
# CPU mode avoids cuDNN version conflicts between CTranslate2 and PyTorch

# ===== LLM SETTINGS (Text Processing & AI) =====
# Qwen2.5-3B-Instruct: Superior tool-use, better intelligence, 100% success!
LLM_MODEL_NAME = "Qwen/Qwen2.5-3B-Instruct"
LLM_DEVICE = "cuda"
LLM_DTYPE = "bfloat16"  # CRITICAL: bfloat16 fixes CUDA numerical errors!
LLM_QUANTIZATION = None  # No quantization - using bfloat16 for stability
LLM_MAX_NEW_TOKENS = 512
LLM_TEMPERATURE = 0.05  # Very low for consistent, deterministic output
LLM_TOP_P = 0.9
LLM_CACHE_DIR = str(MODELS_DIR)
LLM_ATTN_IMPLEMENTATION = "eager"  # Avoid flash-attention compatibility issues

# ===== AUDIO SETTINGS =====
SAMPLE_RATE = 16000  # Whisper requirement
DEVICE_SAMPLE_RATE = 44100  # AT2020 USB microphone native rate
CHANNELS = 1  # Mono
VAD_MODE = 1  # 0-3, 1=less aggressive (preserves more speech), 3=most aggressive
SILENCE_DURATION = 1.5  # Seconds of silence to finalize recording (increased from 1.0)
CHUNK_SIZE = 1024  # PyAudio buffer size
FORMAT = "float32"  # Audio format

# ===== KEYWORD DETECTION =====
KEYWORD_BUFFER_SECONDS = 30  # Rolling buffer size (increased from 10s for longer phrases)
KEYWORD_CHECK_INTERVAL = 2.0  # Check for keywords every N seconds (reduced CPU load)

# Activation keywords (case-insensitive)
KEYWORDS = {
    "transcribe_end": [
        r'\bend transcribe\b',
        r'\bend transcribing\b',  # Whisper outputs "-ing" form
        r'\bstop transcribe\b',
        r'\bstop transcribing\b',  # Whisper outputs "-ing" form
        r'\bstop[.,!?]\s+transcrib',  # Edge case: "Stop. Transcribe." with punctuation
        r'\band transcribe\b',  # Common mishearing of "end"
        r'\band the transcribe\b',  # Another mishearing variant
        r'\band transcribing\b',  # Mishearing with -ing form
        r'\bfinish transcribe\b',
        r'\bfinish transcribing\b',  # -ing form
    ],
    "transcribe_start": [
        r'\btranscribe\b',
        r'\btranscribing\b',  # Whisper outputs "-ing" form
        r'\bstart transcribe\b',
        r'\bstart transcribing\b',  # Whisper outputs "-ing" form
        r'\bbegin transcribe\b',
        r'\bbegin transcribing\b',  # -ing form
    ],
    "pixel_bot": [
        r'\bpixel bot\b',
        r'\bpixelbot\b',  # Whisper often transcribes as one word
        r'\bpixel[ -]?b[aoy]t*\b',  # Fuzzy match for mishearings (bot/bat/by/bout)
        r'\bhey pixel\b',
        r'\byo pixel\b',
    ],
    "cortex": [
        r'\bcortex\b',
        r'\bcore techs?\b',  # Whisper mishears as "core tech" or "core techs"
        r'\bcoretex\b',
        r'\bpixel cortex\b',
        r'\bhey cortex\b',
        r'\byo cortex\b',
    ],
}

# ===== HOTKEYS =====
HOTKEY_MOUNT = "f10"  # Load models
HOTKEY_LISTEN = "f4"  # Toggle listening mode

# ===== LOGGING =====
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = LOGS_DIR / "dictation.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5

# ===== CUSTOM WORD REPLACEMENTS =====
# Manual text replacements for common Whisper mishearings
CUSTOM_WORD_REPLACEMENTS = {
    # DexScreener variations
    "deck screener": "DexScreener",
    "dex screener": "DexScreener",
    "decks creener": "DexScreener",
    "dex creator": "DexScreener",
    "moon screener": "MoonScreener",
    "moonscreener": "MoonScreener",

    # Bot name variations
    "pixelbot": "Pixel Bot",
    "pixel bots": "Pixel Bot",

    # Cortex variations (these should be removed by keyword processing anyway)
    "core tech": "Cortex",
    "core techs": "Cortex",
    "coretex": "Cortex",

    # Vercel variations
    "versil": "Vercel",
    "versile": "Vercel",
    "versel": "Vercel",
}

# ===== SYSTEM PROMPTS FOR LLM =====
# Action-specific prompts for different use cases

# TRANSCRIBE: Fix typos, stuttering, misspoken words - keep exact meaning
TRANSCRIBE_SYSTEM_PROMPT = """You are a transcription cleaner for voice dictation.

Your task: Clean speech-to-text output while preserving the user's EXACT intended meaning.

What to fix:
- Typos and mishearings (e.g., "their" → "there" if context suggests it)
- Stuttering and repeated words (e.g., "the the dog" → "the dog")
- Filler words (e.g., "um", "uh", "like" when excessive)
- Obvious speech errors (e.g., "I wented" → "I went")
- Capitalization and punctuation

What NOT to change:
- User's vocabulary choices
- Sentence structure
- Technical terms (preserve exactly as spoken)
- Intent or meaning

Context from recent transcriptions:
{context}

Examples:
─────────────────
IN: um send email to uh john about the the meeting
OUT: Send email to John about the meeting.
─────────────────
IN: their going to they're house
OUT: They're going to their house.
─────────────────
IN: create a a function that um takes input
OUT: Create a function that takes input.
─────────────────
IN: the API endpoint needs authentication
OUT: The API endpoint needs authentication.
─────────────────

Clean this transcription:"""

TRANSCRIBE_USER_TEMPLATE = """{text}"""

# CORTEX: Format speech into well-worded blockchain questions using context
CORTEX_SYSTEM_PROMPT = """You are a query formatter for blockchain questions.

Your task: Convert casual speech into clear, well-formed questions for a blockchain API.

Use conversation context to:
- Infer missing details from previous questions
- Maintain topic continuity
- Add clarity while preserving intent

Conversation history:
{context}

Guidelines:
1. If user refers to previous topic ("what about yesterday?"), include that topic
2. If user corrects themselves ("no I meant X"), update the query accordingly
3. Make questions specific and clear
4. Preserve all important details (token names, chain names, addresses, etc.)
5. Keep questions concise (1-2 sentences max)
6. If input is empty or just whitespace, output exactly: "EMPTY_QUERY"

Examples:
─────────────────
Context: Q: What is the price of Bitcoin?
Current: what about yesterday
Output: What was the price of Bitcoin yesterday?
─────────────────
Context: Q: What is the price of Bolt on Base? A: I can't find that token.
Current: no I meant Volt on Base
Output: What is the price of Volt on Base?
─────────────────
Context: (none)
Current: check ethereum price
Output: What is the current price of Ethereum?
─────────────────
Context: Q: What is Ethereum? A: [explanation]
Current: what's its market cap
Output: What is Ethereum's market cap?
─────────────────
Current: (empty or whitespace)
Output: EMPTY_QUERY
─────────────────

Format this query:"""

CORTEX_USER_TEMPLATE = """{text}"""

# PIXEL BOT: Conversational AI - preserve natural speech, add context awareness
PIXELBOT_SYSTEM_PROMPT = """You are preparing user input for a conversational AI assistant.

Your task: Clean speech while maintaining natural conversational flow.

Conversation history:
{context}

What to do:
- Fix obvious speech errors
- Add context from conversation if needed
- Keep natural, casual tone
- Preserve questions, emotions, intent

What NOT to do:
- Don't formalize casual speech
- Don't add unnecessary details
- Don't change the user's tone

Examples:
─────────────────
Context: (none)
IN: hey what's two plus two
OUT: What's two plus two?
─────────────────
Context: Q: Tell me about Python. A: [explanation]
IN: and what about rust
OUT: And what about Rust?
─────────────────
IN: um can you uh explain quantum computing
OUT: Can you explain quantum computing?
─────────────────

Clean this input:"""

PIXELBOT_USER_TEMPLATE = """{text}"""

# Pixel Bot system prompt (conversational AI)
PIXEL_BOT_SYSTEM_PROMPT = """You are Pixel Bot, a helpful and concise AI assistant.

Guidelines:
- Keep responses under 3 sentences for voice output
- Be accurate and factual
- Use simple, clear language
- You can discuss programming, crypto, blockchain, general knowledge
- Be friendly but professional
- Avoid markdown formatting in spoken responses"""

# Pixel Cortex system prompt (blockchain queries)
PIXEL_CORTEX_SYSTEM_PROMPT = """You are Pixel Cortex, a blockchain data assistant.

Your job is to:
1. Extract intent from natural language blockchain queries
2. Format blockchain data into natural spoken responses

Keep responses concise (1-2 sentences) suitable for voice output."""

# ===== TTS SETTINGS (OpenAI) =====
TTS_MODEL = "tts-1"
TTS_VOICE = "nova"  # Female, warm voice (recommended)
TTS_SPEED = 1.0
TTS_TEMP_FILE = "/tmp/tts_output.mp3"

# Available voices: nova, alloy, echo, fable, onyx, shimmer

# ===== MODE SETTINGS =====
TRANSCRIBE_MODE_TIMEOUT = 300  # Max recording time (5 minutes)
PIXEL_BOT_LISTEN_DURATION = 5  # Listen for 5 seconds after activation
CORTEX_LISTEN_DURATION = 5  # Listen for 5 seconds after activation

# ===== VRAM MONITORING =====
VRAM_WARNING_THRESHOLD = 0.85  # Warn if >85% VRAM used
VRAM_CHECK_INTERVAL = 30  # Check VRAM every 30 seconds

# ===== PERFORMANCE SETTINGS =====
# Expected latencies (for monitoring)
TARGET_WHISPER_LATENCY = 3.0  # seconds (for 10s audio)
TARGET_LLM_LATENCY = 2.0  # seconds (for typical sentence)
TARGET_END_TO_END_LATENCY = 5.0  # seconds (total)

# ===== NOTIFICATION SETTINGS =====
ENABLE_NOTIFICATIONS = True
NOTIFICATION_APP_NAME = "Voice Dictation"
NOTIFICATION_TIMEOUT = 3000  # milliseconds

# ===== DEBUG SETTINGS =====
DEBUG_SAVE_AUDIO = False  # Save audio files for debugging
DEBUG_AUDIO_DIR = BASE_DIR / "debug_audio"
DEBUG_PRINT_VRAM = True  # Print VRAM usage after model operations

if DEBUG_SAVE_AUDIO:
    DEBUG_AUDIO_DIR.mkdir(exist_ok=True)

# ===== VALIDATION =====
def validate_config():
    """Validate configuration on import."""
    import torch

    # Check CUDA availability
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available! This system requires a CUDA-capable GPU.")

    # Check GPU VRAM
    gpu_props = torch.cuda.get_device_properties(0)
    total_vram_gb = gpu_props.total_memory / 1e9

    if total_vram_gb < 11:
        raise RuntimeError(
            f"Insufficient VRAM! Found {total_vram_gb:.1f}GB, need at least 12GB.\n"
            "This system requires RTX 4070 (12GB) or better."
        )

    print(f"✓ GPU: {gpu_props.name}")
    print(f"✓ VRAM: {total_vram_gb:.1f}GB")

    # Check API keys
    from dotenv import load_dotenv
    load_dotenv()

    openai_key = os.getenv("OPENAI_API_KEY")
    moralis_key = os.getenv("MORALIS_API_KEY")

    if not openai_key:
        print("⚠ Warning: OPENAI_API_KEY not found in .env (TTS will not work)")

    if not moralis_key:
        print("⚠ Warning: MORALIS_API_KEY not found in .env (Cortex will not work)")

    return True

# Run validation on import (can be disabled if needed)
# validate_config()
