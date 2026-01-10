"""
Mode Manager - Push-to-Talk

Simplified push-to-talk system:
1. Press F4 to START recording
2. Press F4 again to STOP recording and process
3. System transcribes, detects keywords, and routes accordingly
"""
import logging
from enum import Enum
from typing import Optional
import re

import numpy as np

from src import config
from src.audio_capture import AudioCapture
from src.transcription_engine import TranscriptionEngine
from src.text_processor import TextProcessor
from src.text_injector import TextInjector
from src.pixel_bot.core import PixelBotCore
from src.pixel_cortex import PixelCortex
from src.notifier import Notifier

logger = logging.getLogger(__name__)


class RecordingState(Enum):
    """Recording states."""
    IDLE = "idle"
    RECORDING = "recording"


class ModeManager:
    """Manages push-to-talk recording and audio processing."""

    def __init__(
        self,
        transcription_engine: TranscriptionEngine,
        text_processor: TextProcessor,
        text_injector: TextInjector,
        pixel_bot: Optional[PixelBotCore] = None,
        pixel_cortex: Optional[PixelCortex] = None,
        notifier: Optional[Notifier] = None,
    ):
        """
        Initialize mode manager.

        Args:
            transcription_engine: Transcription engine instance
            text_processor: Text processor instance
            text_injector: Text injector instance
            pixel_bot: Optional Pixel Bot instance
            pixel_cortex: Optional Pixel Cortex instance
            notifier: Optional notifier instance
        """
        self.transcription_engine = transcription_engine
        self.text_processor = text_processor
        self.text_injector = text_injector
        self.pixel_bot = pixel_bot
        self.pixel_cortex = pixel_cortex
        self.notifier = notifier

        # Audio capture
        self.audio_capture: Optional[AudioCapture] = None

        # Recording state
        self.state = RecordingState.IDLE
        self.recording_start_time = None

        # Last action tracking (for fallback when no keyword detected)
        self.last_action = "transcribe"  # Default to transcribe

        logger.info("ModeManager initialized (push-to-talk, action-aware)")

    def initialize(self) -> bool:
        """
        Initialize mode manager components.

        Returns:
            bool: True if successful
        """
        try:
            logger.info("Initializing mode manager...")

            # Initialize audio capture
            self.audio_capture = AudioCapture()
            if not self.audio_capture.start():
                logger.error("Failed to start audio capture")
                return False

            logger.info("✓ Mode manager initialized")
            logger.info("✓ Press F4 to start/stop recording")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize mode manager: {e}", exc_info=True)
            return False

    def shutdown(self) -> bool:
        """
        Shutdown mode manager.

        Returns:
            bool: True if successful
        """
        try:
            logger.info("Shutting down mode manager...")

            # Stop any active recording
            if self.state == RecordingState.RECORDING:
                self.audio_capture.stop_recording()

            if self.audio_capture:
                self.audio_capture.stop()

            logger.info("✓ Mode manager shutdown")
            return True

        except Exception as e:
            logger.error(f"Failed to shutdown mode manager: {e}", exc_info=True)
            return False

    def toggle_recording(self):
        """
        Toggle recording on/off (F4 hotkey handler).

        When starting: Begin recording
        When stopping: Transcribe, detect keywords, and route accordingly
        """
        if self.state == RecordingState.IDLE:
            # START RECORDING
            self._start_recording()
        else:
            # STOP RECORDING AND PROCESS
            self._stop_and_process()

    def _start_recording(self):
        """Start recording audio."""
        try:
            # INTERRUPT ANY PLAYING TTS
            # User pressed F4 while TTS is speaking - stop it immediately
            if self.pixel_bot and self.pixel_bot.tts:
                self.pixel_bot.tts.stop_audio()
            if self.pixel_cortex and self.pixel_cortex.tts:
                self.pixel_cortex.tts.stop_audio()

            logger.info("🔴 RECORDING STARTED")

            # Notify user
            if self.notifier:
                self.notifier.notify("🔴 Recording", "Press F4 again to stop")

            # Start recording
            self.audio_capture.start_recording()
            self.state = RecordingState.RECORDING

            import time
            self.recording_start_time = time.time()

        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            self.state = RecordingState.IDLE

    def _stop_and_process(self):
        """Stop recording and process the audio."""
        try:
            # Calculate recording duration
            import time
            duration = time.time() - self.recording_start_time if self.recording_start_time else 0

            logger.info(f"⏹️  RECORDING STOPPED (duration: {duration:.1f}s)")

            # Stop recording and get audio
            audio = self.audio_capture.stop_recording()
            self.state = RecordingState.IDLE

            if audio is None or len(audio) == 0:
                logger.warning("No audio captured")
                if self.notifier:
                    self.notifier.notify("⚠️ No Audio", "Recording was empty")
                return

            # Notify transcribing with audio duration
            audio_duration = len(audio) / config.SAMPLE_RATE
            if self.notifier:
                self.notifier.notify_transcribing(duration=audio_duration)

            logger.info(f"Processing {len(audio) / config.SAMPLE_RATE:.1f}s of audio")

            # Transcribe audio
            text, info = self.transcription_engine.transcribe(audio)

            if not text or not text.strip():
                logger.warning("Transcription was empty")
                if self.notifier:
                    self.notifier.notify("⚠️ Empty", "No speech detected")
                return

            logger.info(f"Transcription: '{text}'")

            # Detect keywords and route
            self._route_by_keywords(text)

        except Exception as e:
            logger.error(f"Failed to process recording: {e}", exc_info=True)
            self.state = RecordingState.IDLE

    def _remove_activation_keywords(self, text: str, keyword_type: str) -> str:
        """
        Remove activation keywords using simple regex (NO LLM!).

        The LLM halluccinates and changes actual content - we ONLY want to remove keywords.

        Args:
            text: Raw transcription with activation keyword
            keyword_type: Type of keyword to remove ("pixelbot" or "cortex")

        Returns:
            str: Text with activation keywords removed
        """
        if keyword_type == "pixelbot":
            # Remove Pixel Bot activation keywords (including common misheard variants)
            patterns = [
                r'\bpixel\s*bot\b',
                r'\bpixelbot\b',
                r'\bpixel-bot\b',       # Whisper transcribes with hyphen
                r'\bpixel\s*-\s*bot\b', # Handles "pixel - bot" spacing
                r'\bhey\s+pixel\b',
                r'\byo\s+pixel\b',
                r'\bpixel\s*back\b',    # Common misheard
                r'\bpixel\s*bach\b',    # Common misheard
                r'\bpixel\s*by\b',      # Common misheard
                r'\bpixel\s*bight\b',   # Common misheard
                r'\bpixel\s*bar\b',     # Common misheard
            ]
        elif keyword_type == "cortex":
            # Remove Cortex activation keywords
            patterns = [
                r'\bcortex\b',
                r'\bcore\s+techs?\b',
                r'\bpixel\s+cortex\b',
                r'\bhey\s+cortex\b',
                r'\byo\s+cortex\b',
            ]
        else:
            return text

        # Remove each pattern
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Clean up extra spaces and punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Multiple spaces to single
        cleaned = re.sub(r'^\s*,\s*', '', cleaned)  # Leading comma
        cleaned = cleaned.strip()

        # Capitalize first letter if needed
        if cleaned and cleaned[0].islower():
            cleaned = cleaned[0].upper() + cleaned[1:]

        return cleaned

    def _route_by_keywords(self, text: str):
        """
        Route audio based on detected keywords.

        Priority:
        1. If keywords present, use first keyword detected (reading left-to-right)
        2. If no keywords, use last action user performed

        Args:
            text: Transcribed text
        """
        text_lower = text.lower()

        # Define keyword patterns for each action
        # Order matters - these are checked left-to-right in text
        keyword_patterns = {
            "pixelbot": [
                r'\bpixel\s*bot\b',
                r'\bpixelbot\b',
                r'\bpixel-bot\b',         # Whisper often transcribes with hyphen
                r'\bpixel\s*-\s*bot\b',   # Handles "pixel - bot" or "pixel- bot"
                r'\bhey\s+pixel\b',
                r'\byo\s+pixel\b',
                r'\bpixel\s*back\b',      # Common misheard
                r'\bpixel\s*bach\b',      # Common misheard
                r'\bpixel\s*by\b',        # Common misheard
                r'\bpixel\s*bight\b',     # Common misheard
                r'\bpixel\s*bar\b',       # Common misheard
            ],
            "cortex": [
                r'\bcortex\b',
                r'\bcore\s+techs?\b',
                r'\bpixel\s+cortex\b',
                r'\bhey\s+cortex\b',
                r'\byo\s+cortex\b',
            ],
            "transcribe": [
                r'\btranscrib\w*\b',  # Catches transcribe, transcribing, etc.
                r'\bstart\s+transcrib\w*\b',
                r'\bstop\s+transcrib\w*\b',
                r'\bend\s+transcrib\w*\b',
            ]
        }

        # Find first keyword position (if any)
        detected_action = None
        first_position = len(text)  # Start at end

        for action, patterns in keyword_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match and match.start() < first_position:
                    first_position = match.start()
                    detected_action = action

        # Route based on detected action or fallback to last action
        if detected_action == "pixelbot":
            logger.info("Detected: Pixel Bot activation (keyword found)")
            self._handle_pixel_bot(text)
        elif detected_action == "cortex":
            logger.info("Detected: Cortex activation (keyword found)")
            self._handle_cortex(text)
        elif detected_action == "transcribe":
            logger.info("Detected: Transcription (keyword found)")
            self._handle_transcription(text)
        else:
            # No keywords detected - use last action
            logger.info(f"No keywords detected - using last action: {self.last_action}")
            if self.last_action == "pixelbot":
                self._handle_pixel_bot(text)
            elif self.last_action == "cortex":
                self._handle_cortex(text)
            else:
                self._handle_transcription(text)

    def _handle_transcription(self, text: str):
        """
        Handle transcription - clean text and type it.

        Args:
            text: Raw transcription
        """
        try:
            logger.info(f"Raw text: '{text}'")

            # Clean text (remove keywords) with transcribe action
            cleaned_text = self.text_processor.process(text, action="transcribe")

            if not cleaned_text or not cleaned_text.strip():
                logger.warning("Cleaned text was empty")
                if self.notifier:
                    self.notifier.notify("⚠️ Empty", "Text was empty after cleaning")
                return

            logger.info(f"Cleaned text: '{cleaned_text}'")

            # Update last action
            self.last_action = "transcribe"

            # Notify
            if self.notifier:
                self.notifier.notify("⌨️ Typing", cleaned_text[:50] + "...")

            # Type the text
            self.text_injector.type_text(cleaned_text)

            logger.info("✓ Text typed successfully")

        except Exception as e:
            logger.error(f"Failed to handle transcription: {e}", exc_info=True)

    def _handle_pixel_bot(self, text: str):
        """
        Handle Pixel Bot query.

        Args:
            text: Raw transcription with Pixel Bot activation
        """
        try:
            if not self.pixel_bot:
                logger.warning("Pixel Bot not initialized")
                return

            logger.info(f"Pixel Bot query: '{text}'")

            # Remove activation keywords using simple regex (NO LLM - it hallucinates!)
            cleaned_text = self._remove_activation_keywords(text, keyword_type="pixelbot")

            if not cleaned_text or not cleaned_text.strip():
                logger.warning("Query was empty after cleaning")
                if self.notifier:
                    self.notifier.notify("⚠️ Empty", "No query detected")
                return

            logger.info(f"Cleaned query: '{cleaned_text}'")

            # Update last action
            self.last_action = "pixelbot"

            # Notify Pixel Bot thinking
            if self.notifier:
                self.notifier.notify_pixelbot_thinking()

            # Query Pixel Bot
            response = self.pixel_bot.chat(cleaned_text, speak_response=True)

            logger.info(f"Pixel Bot response: '{response}'")

        except Exception as e:
            logger.error(f"Failed to handle Pixel Bot: {e}", exc_info=True)

    def _handle_cortex(self, text: str):
        """
        Handle Cortex blockchain query.

        Args:
            text: Raw transcription with Cortex activation
        """
        try:
            if not self.pixel_cortex:
                logger.warning("Pixel Cortex not initialized")
                return

            logger.info(f"Cortex query: '{text}'")

            # Remove activation keywords using simple regex (NO LLM - it hallucinates!)
            cleaned_text = self._remove_activation_keywords(text, keyword_type="cortex")

            if not cleaned_text or not cleaned_text.strip():
                logger.warning("Query was empty after cleaning")
                if self.notifier:
                    self.notifier.notify("⚠️ Empty", "No query detected")
                return

            logger.info(f"Cleaned query: '{cleaned_text}'")

            # Update last action
            self.last_action = "cortex"

            # Notify Cortex thinking
            if self.notifier:
                self.notifier.notify_cortex_thinking()

            # Query Cortex
            response = self.pixel_cortex.query(cleaned_text, speak_response=True)

            logger.info(f"Cortex response: '{response}'")

        except Exception as e:
            logger.error(f"Failed to handle Cortex: {e}", exc_info=True)

    def get_state(self) -> str:
        """Get current recording state."""
        return self.state.value
