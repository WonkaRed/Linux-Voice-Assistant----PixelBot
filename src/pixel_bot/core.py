"""
Pixel Bot Core - Main orchestrator for Pixel Bot functionality.

NEW ARCHITECTURE (Intelligent):
- Two-tier routing: Fast path (regex) + Intelligent path (LLM + function calling)
- Tool arsenal for complex queries
- Function calling with Qwen2.5
"""
import logging
import re
from typing import Optional, Dict, Any

from src.llm_manager import LLMManager
from src.tts_engine import TTSEngine

logger = logging.getLogger(__name__)


class PixelBotCore:
    """
    Intelligent voice assistant with two-tier routing.

    NEW Architecture:
    1. Fast Path: Regex for instant simple commands (mute, volume, basic math)
    2. Intelligent Path: LLM + function calling for complex queries
    3. Tool Arsenal: Advanced system stats, web search, command execution, files
    4. TTS for voice responses
    """

    def __init__(self, llm_manager: LLMManager, tts_engine: Optional[TTSEngine] = None):
        """
        Initialize Pixel Bot.

        Args:
            llm_manager: LLM manager for function calling
            tts_engine: Optional TTS engine for voice responses
        """
        self.llm = llm_manager
        self.tts = tts_engine

        # Components (initialized lazily)
        self._handlers = {}
        self._tool_registry = None
        self._router = None
        self._initialized = False

        logger.info("Pixel Bot Core initialized (intelligent mode)")

    def _initialize(self):
        """Lazy initialization of components."""
        if self._initialized:
            return

        logger.info("Initializing Pixel Bot components...")

        # Import components
        from .handlers.volume_control import VolumeControlHandler
        from .handlers.system_stats import SystemStatsHandler
        from .handlers.app_launcher import AppLauncherHandler
        from .handlers.math_calculator import MathCalculatorHandler
        from .tools import (
            ToolRegistry,
            SystemStatsTool,
            WebSearchTool,
            ExecuteCommandTool,
            SearchFilesTool,
            ReadFileTool,
            VolumeControlTool,
            MathCalculatorTool
        )
        from .intelligent_router import IntelligentRouter

        # Initialize handlers (for fast path)
        self._handlers = {
            'volume_control': VolumeControlHandler(self.llm, self.tts),
            'system_stats': SystemStatsHandler(self.llm, self.tts),
            'app_launcher': AppLauncherHandler(self.llm, self.tts),
            'math_calculator': MathCalculatorHandler(self.llm, self.tts),
        }

        # Initialize tools (for intelligent path)
        self._tool_registry = ToolRegistry()
        self._tool_registry.register_tool(SystemStatsTool())
        self._tool_registry.register_tool(WebSearchTool())
        self._tool_registry.register_tool(ExecuteCommandTool())
        self._tool_registry.register_tool(SearchFilesTool())
        self._tool_registry.register_tool(ReadFileTool())
        self._tool_registry.register_tool(VolumeControlTool())
        self._tool_registry.register_tool(MathCalculatorTool())

        # Initialize router (local models only - no external dependencies)
        self._router = IntelligentRouter(
            llm_manager=self.llm,
            tool_registry=self._tool_registry,
            handlers=self._handlers,
            tts_engine=self.tts
        )

        self._initialized = True
        logger.info(f"✓ Initialized {len(self._handlers)} handlers and {self._tool_registry.get_tool_count()} tools")

    def chat(self, query: str, speak_response: bool = True) -> str:
        """
        Process a user query and execute appropriate action.

        NEW: Uses intelligent router for two-tier routing.

        Args:
            query: User's voice query
            speak_response: Whether to speak the response

        Returns:
            str: Response text
        """
        if not query or not query.strip():
            logger.warning("Empty query provided to Pixel Bot")
            return ""

        try:
            logger.info(f"Pixel Bot query: '{query}'")

            # Ensure components are initialized
            self._initialize()

            # Route using intelligent router
            response = self._router.route(query, speak_response)

            logger.info(f"Pixel Bot response: '{response}'")
            return response

        except Exception as e:
            logger.error(f"Pixel Bot failed: {e}", exc_info=True)
            error_msg = "Sorry, I encountered an error."

            if speak_response and self.tts and self.tts.is_available:
                self.tts.speak_async(error_msg)

            return error_msg

    def get_status(self) -> Dict[str, Any]:
        """
        Get Pixel Bot status.

        Returns:
            dict: Status information
        """
        return {
            "initialized": self._initialized,
            "handlers_count": len(self._handlers) if self._initialized else 0,
            "tools_count": self._tool_registry.get_tool_count() if self._tool_registry else 0,
            "llm_ready": self.llm.is_loaded if self.llm else False,
            "tts_available": self.tts.is_available if self.tts else False,
            "architecture": "intelligent (two-tier routing)"
        }
