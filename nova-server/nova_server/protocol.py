"""
Nova Protocol — Message types and serialization for WebSocket communication.

All messages are JSON with a "type" field.
"""
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# --- Node → Server Messages ---

@dataclass
class HelloMessage:
    """Authentication message sent by node on connect."""
    node_id: str
    token: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    type: str = "hello"


@dataclass
class TranscriptionMessage:
    """Transcribed speech from STT."""
    text: str
    audio_duration_s: float = 0.0
    stt_latency_s: float = 0.0
    type: str = "transcription"


@dataclass
class ToolResultMessage:
    """Tool execution result from node."""
    request_id: str
    result: str
    type: str = "tool_result"


@dataclass
class VRAMStatusMessage:
    """VRAM status report from node."""
    free_gb: float
    used_gb: float
    total_gb: float
    models_loaded: List[str] = field(default_factory=list)
    external_processes: List[Dict[str, Any]] = field(default_factory=list)
    type: str = "vram_status"


@dataclass
class PongMessage:
    """Pong response to server ping."""
    type: str = "pong"


# --- Server → Node Messages ---

@dataclass
class WelcomeMessage:
    """Welcome after successful auth."""
    session_id: str
    type: str = "welcome"


@dataclass
class SpeakMessage:
    """Speak text via TTS."""
    text: str
    type: str = "speak"


@dataclass
class ToolRequestMessage:
    """Execute a local tool on the node."""
    tool: str
    params: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "tool_request"


@dataclass
class ModelCommandMessage:
    """Model management command."""
    action: str  # load_stt, unload_stt, load_tts, unload_tts, unload_all
    type: str = "model_command"


@dataclass
class PingMessage:
    """Keepalive ping."""
    type: str = "ping"


@dataclass
class ErrorMessage:
    """Error message."""
    message: str
    type: str = "error"


# --- Serialization ---

def encode(msg) -> str:
    """Encode a dataclass message to JSON string."""
    return json.dumps(asdict(msg))


def decode(raw: str) -> Dict[str, Any]:
    """Decode a JSON string to a dict. Raises ValueError on invalid JSON."""
    return json.loads(raw)


# Message type registry for validation
VALID_NODE_TYPES = {"hello", "transcription", "tool_result", "vram_status", "pong"}
VALID_SERVER_TYPES = {"welcome", "speak", "tool_request", "model_command", "ping", "error"}


def validate_message(data: Dict[str, Any], source: str = "node") -> bool:
    """Validate a message dict has required fields."""
    msg_type = data.get("type")
    if not msg_type:
        return False

    valid_types = VALID_NODE_TYPES if source == "node" else VALID_SERVER_TYPES
    if msg_type not in valid_types:
        return False

    # Check required fields per type
    required = {
        "hello": ["node_id", "token"],
        "transcription": ["text"],
        "tool_result": ["request_id", "result"],
        "vram_status": ["free_gb", "used_gb", "total_gb"],
        "speak": ["text"],
        "tool_request": ["tool", "request_id"],
        "model_command": ["action"],
        "error": ["message"],
    }

    for field_name in required.get(msg_type, []):
        if field_name not in data:
            return False

    return True
