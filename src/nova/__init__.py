"""
Nova Voice Assistant — GPU Node + Server architecture.

Desktop GPU Node:
- Faster-whisper large-v3 STT (CUDA, float16)
- Piper TTS (ryan-high)
- VRAM-submissive model management
- 4 local tools: system_stats, clipboard, timer, notes
- WebSocket connection to Nova Server

Nova Server (10.0.0.75):
- Agent routing + Pixel Bot (LOCAL, no SSH)
- Orchestrates voice queries
"""

__version__ = "2.0.0"
