#!/usr/bin/env python3
"""
AI Voice Dictation System - Main Daemon

Dual-model architecture optimized for RTX 4070 12GB:
- Whisper base.en (CPU mode, 0.5GB) for speech recognition
- Qwen2.5-1.5B-Instruct (GPU bfloat16, 3.6GB) for text processing & AI features

Total VRAM: ~4.1GB (66% safety margin)

Usage:
    python dictation_daemon.py
    or
    ./run.sh

Hotkeys:
    F10 - Unmount/Remount models (models load automatically on startup)
    F4  - START/STOP recording (push-to-talk)
"""
import logging
import signal
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src import config
from src.transcription_engine import TranscriptionEngine
from src.text_processor import TextProcessor
from src.text_injector import TextInjector
from src.llm_manager import LLMManager
from src.pixel_bot.core import PixelBotCore
from src.pixel_cortex import PixelCortex
from src.tts_engine import TTSEngine
from src.notifier import Notifier
from src.hotkey_listener import HotkeyListener
from src.mode_manager import ModeManager

logger = logging.getLogger(__name__)


class DictationDaemon:
    """Main daemon orchestrating the voice dictation system."""

    def __init__(self):
        """Initialize daemon."""
        self.is_running = False
        self.models_loaded = False

        # Core components
        self.transcription_engine: TranscriptionEngine = None
        self.text_processor: TextProcessor = None
        self.text_injector: TextInjector = None
        self.llm_manager: LLMManager = None
        self.pixel_bot: PixelBot = None
        self.pixel_cortex: PixelCortex = None
        self.tts_engine: TTSEngine = None
        self.notifier: Notifier = None
        self.hotkey_listener: HotkeyListener = None
        self.mode_manager: ModeManager = None

        logger.info("DictationDaemon initialized")

    def start(self):
        """Start the daemon."""
        try:
            logger.info("=" * 70)
            logger.info("AI VOICE DICTATION SYSTEM")
            logger.info("=" * 70)
            logger.info(f"Whisper: {config.WHISPER_MODEL_SIZE} (CPU mode)")
            logger.info(f"LLM: {config.LLM_MODEL_NAME}")
            logger.info(f"VRAM Target: ~4.1GB (Whisper 0.5GB + Qwen2.5 3.6GB)")
            logger.info("=" * 70)

            self.is_running = True

            # Initialize non-model components first
            logger.info("\n1. Initializing core components...")
            self._initialize_core_components()

            # Load models on startup
            logger.info("\n2. Loading models on startup...")
            self._load_models()

            # Set up hotkey listener
            logger.info("\n3. Setting up hotkey listener...")
            self.hotkey_listener = HotkeyListener(
                on_mount=self._on_mount_key,
                on_toggle=self._on_toggle_key,
            )
            self.hotkey_listener.start()

            logger.info("\n" + "=" * 70)
            logger.info("✅ SYSTEM READY")
            logger.info("=" * 70)
            logger.info(f"Press {config.HOTKEY_MOUNT.upper()} to unmount/remount models")
            logger.info(f"Press {config.HOTKEY_LISTEN.upper()} to start/stop recording (push-to-talk)")
            logger.info(f"Press Ctrl+C to exit")
            logger.info("=" * 70)

            # Keep running
            self._run_main_loop()

        except KeyboardInterrupt:
            logger.info("\nReceived interrupt signal")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            self.shutdown()

    def _initialize_core_components(self):
        """Initialize components that don't require models."""
        # Text injector (no dependencies)
        self.text_injector = TextInjector()

        # Notifier (optional)
        self.notifier = Notifier()

        # TTS engine (optional, for Pixel Bot)
        self.tts_engine = TTSEngine()

        logger.info("✓ Core components initialized")

    def _load_models(self):
        """Load AI models (Whisper + LLM)."""
        logger.info("\n" + "=" * 70)
        logger.info("LOADING MODELS")
        logger.info("=" * 70)

        try:
            # Load Whisper
            logger.info("\n[1/3] Loading Whisper base.en...")
            self.transcription_engine = TranscriptionEngine()
            if not self.transcription_engine.initialize():
                logger.error("Failed to load Whisper")
                if self.notifier:
                    self.notifier.notify_error("Startup Error", "Failed to load Whisper")
                return False

            logger.info("✓ Whisper loaded")
            if self.notifier:
                self.notifier.notify_model_loaded("Whisper base.en", vram=0.5)

            # Load LLM (Qwen2.5)
            logger.info("\n[2/3] Loading Qwen2.5-1.5B (bfloat16)...")
            logger.info("   This may take 30-60 seconds on first run...")
            self.llm_manager = LLMManager()
            if not self.llm_manager.load():
                logger.warning("LLM failed to load - using regex-only mode")
                self.llm_manager = None
                # Initialize text processor without LLM
                self.text_processor = TextProcessor(use_llm=False)
            else:
                logger.info(f"✓ LLM loaded ({self.llm_manager.vram_usage:.2f}GB VRAM)")
                if self.notifier:
                    self.notifier.notify_model_loaded(
                        "Qwen2.5-3B-Instruct",
                        vram=self.llm_manager.vram_usage
                    )

                # Initialize text processor WITH LLM
                self.text_processor = TextProcessor(llm_manager=self.llm_manager, use_llm=True)

                # Initialize Pixel Bot Core (with advanced handlers)
                self.pixel_bot = PixelBotCore(llm_manager=self.llm_manager, tts_engine=self.tts_engine)
                logger.info("✓ Pixel Bot Core ready (volume, stats, apps, math)")

                # Initialize Pixel Cortex
                self.pixel_cortex = PixelCortex(self.llm_manager, self.tts_engine)
                logger.info("✓ Pixel Cortex ready")

            self.text_processor.initialize()

            # Initialize mode manager
            logger.info("\n[3/3] Starting mode manager...")
            self.mode_manager = ModeManager(
                transcription_engine=self.transcription_engine,
                text_processor=self.text_processor,
                text_injector=self.text_injector,
                pixel_bot=self.pixel_bot,
                pixel_cortex=self.pixel_cortex,
                notifier=self.notifier,
            )

            if not self.mode_manager.initialize():
                logger.error("Failed to initialize mode manager")
                return False

            logger.info("✓ Mode manager started")

            self.models_loaded = True

            logger.info("\n" + "=" * 70)
            logger.info("✅ ALL SYSTEMS OPERATIONAL")
            logger.info("=" * 70)
            logger.info("PUSH-TO-TALK MODE:")
            logger.info("  1. Press F4 to START recording")
            logger.info("  2. Speak your command")
            logger.info("  3. Press F4 to STOP and process")
            logger.info("")
            logger.info("What you can say:")
            logger.info("  • 'hello world' - Dictation (default)")
            logger.info("  • 'transcribe hello world' - Dictation (keyword removed)")
            logger.info("  • 'pixel bot set volume to 50' - Control volume")
            logger.info("  • 'pixel bot what's my CPU usage' - System stats")
            logger.info("  • 'pixel bot open brave' - Launch apps")
            logger.info("  • 'pixel bot what's 5 times 8' - Math calculations")
            logger.info("  • 'cortex what is blockchain' - Blockchain queries")
            logger.info("")
            logger.info("Keywords like 'transcribe', 'pixel bot', and 'cortex' are")
            logger.info("automatically detected and routed to the right system.")
            logger.info("=" * 70)

            # Notify success
            if self.notifier:
                self.notifier.notify_models_loaded()

            return True

        except Exception as e:
            logger.error(f"Failed to load models: {e}", exc_info=True)
            if self.notifier:
                self.notifier.notify_error("Startup Error", str(e))
            return False

    def _unload_models(self):
        """Unload AI models to free VRAM."""
        logger.info("\n" + "=" * 70)
        logger.info("UNLOADING MODELS")
        logger.info("=" * 70)

        try:
            # Stop mode manager
            if self.mode_manager:
                self.mode_manager.shutdown()
                self.mode_manager = None

            # Unload models
            if self.transcription_engine:
                self.transcription_engine.shutdown()
                self.transcription_engine = None
                if self.notifier:
                    self.notifier.notify_model_unloaded("Whisper base.en")

            if self.llm_manager:
                self.llm_manager.unload()
                self.llm_manager = None
                if self.notifier:
                    self.notifier.notify_model_unloaded("Qwen2.5-3B-Instruct")

            # Clear text processor
            if self.text_processor:
                self.text_processor.shutdown()
                self.text_processor = None

            # Clear AI features
            self.pixel_bot = None
            self.pixel_cortex = None

            self.models_loaded = False

            logger.info("✓ Models unloaded")
            logger.info(f"Press {config.HOTKEY_MOUNT.upper()} to reload models")
            logger.info("=" * 70)

            if self.notifier:
                self.notifier.notify("Models Unloaded", "Press F10 to reload")

        except Exception as e:
            logger.error(f"Error unloading models: {e}", exc_info=True)

    def _on_mount_key(self):
        """Handle F10 key press (unmount/remount models)."""
        if self.models_loaded:
            logger.info("\nF10 pressed - Unloading models...")
            self._unload_models()
        else:
            logger.info("\nF10 pressed - Reloading models...")
            self._load_models()

    def _on_toggle_key(self):
        """Handle F4 key press (toggle recording - push-to-talk)."""
        if not self.models_loaded:
            logger.warning("Models not loaded yet - press F10 first")
            if self.notifier:
                self.notifier.notify("⚠️ Not Ready", "Press F10 to load models first")
            return

        if not self.mode_manager:
            logger.error("Mode manager not initialized")
            return

        # Toggle recording (start/stop)
        self.mode_manager.toggle_recording()

    def _run_main_loop(self):
        """Main event loop."""
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nShutting down...")

    def shutdown(self):
        """Shutdown daemon and cleanup."""
        logger.info("\nShutting down daemon...")

        self.is_running = False

        # Stop mode manager
        if self.mode_manager:
            self.mode_manager.shutdown()

        # Stop hotkey listener
        if self.hotkey_listener:
            self.hotkey_listener.stop()

        # Unload models
        if self.transcription_engine:
            self.transcription_engine.shutdown()

        if self.llm_manager:
            self.llm_manager.unload()

        logger.info("✓ Daemon shutdown complete")


def setup_logging():
    """Configure logging."""
    # Create logs directory
    config.LOGS_DIR.mkdir(exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT,
        handlers=[
            logging.FileHandler(config.LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ]
    )

    logger.info("Logging configured")


def main():
    """Main entry point."""
    # Setup logging
    setup_logging()

    # Validate configuration
    try:
        config.validate_config()
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        sys.exit(1)

    # Create and start daemon
    daemon = DictationDaemon()

    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"\nReceived signal {sig}")
        daemon.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start daemon
    daemon.start()


if __name__ == "__main__":
    main()
