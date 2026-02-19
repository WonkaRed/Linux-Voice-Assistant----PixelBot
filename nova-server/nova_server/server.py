"""
Nova WebSocket Server — Brain of Nova voice assistant.

Orchestrates voice queries between desktop GPU node and Pixel Bot.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import websockets
from websockets.asyncio.server import serve, ServerConnection

from .agent import ServerAgent
from .auth import TokenAuth
from .config import ServerConfig
from .pixelbot import PixelBotClient
from .protocol import (
    decode, encode, validate_message,
    WelcomeMessage, SpeakMessage, ToolRequestMessage,
    PingMessage, ErrorMessage,
)

logger = logging.getLogger(__name__)


@dataclass
class ConnectedNode:
    """A connected desktop GPU node."""
    ws: ServerConnection
    node_id: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    vram_status: Optional[Dict[str, Any]] = None


class NovaServer:
    """WebSocket server that orchestrates Nova voice queries."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.auth = TokenAuth(config.auth_token)
        self.nodes: Dict[str, ConnectedNode] = {}
        self._pending_tools: Dict[str, asyncio.Future] = {}

        # Initialize Pixel Bot client (LOCAL, no SSH!)
        pb_config = config.pixelbot
        self.pixelbot = PixelBotClient(
            agent_name=pb_config.get("agent_name", "main"),
            session_id=pb_config.get("session_id", "nova-desktop"),
            timeout=pb_config.get("timeout", 15),
            max_retries=pb_config.get("max_retries", 1),
            retry_delay=pb_config.get("retry_delay", 2.0),
            soul_dir=config.soul_dir,
        )

        # Initialize agent with tool request callback
        self.agent = ServerAgent(
            pixelbot=self.pixelbot,
            request_tool=self._request_tool_from_node,
        )

        logger.info(f"NovaServer initialized (port={config.port})")

    async def _request_tool_from_node(self, tool: str, params: Dict[str, Any]) -> str:
        """Request tool execution from the connected desktop node."""
        node = self._get_primary_node()
        if not node:
            return f"ERROR: No desktop node connected — can't execute {tool}"

        msg = ToolRequestMessage(tool=tool, params=params)
        request_id = msg.request_id

        # Create a future to await the result
        future = asyncio.get_event_loop().create_future()
        self._pending_tools[request_id] = future

        try:
            await node.ws.send(encode(msg))
            logger.debug(f"Sent tool_request {request_id}: {tool}")

            # Wait for result with timeout
            result = await asyncio.wait_for(future, timeout=10.0)
            return result

        except asyncio.TimeoutError:
            logger.warning(f"Tool request {request_id} timed out")
            return f"ERROR: Tool {tool} timed out on desktop node"

        finally:
            self._pending_tools.pop(request_id, None)

    def _get_primary_node(self) -> Optional[ConnectedNode]:
        """Get the primary connected node."""
        if not self.nodes:
            return None
        return next(iter(self.nodes.values()))

    async def handle_connection(self, ws: ServerConnection):
        """Handle a new WebSocket connection."""
        node: Optional[ConnectedNode] = None
        remote = ws.remote_address

        try:
            # Wait for hello message (auth)
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            data = decode(raw)

            if data.get("type") != "hello":
                await ws.send(encode(ErrorMessage(message="Expected hello message")))
                return

            if not self.auth.verify(data.get("token", "")):
                await ws.send(encode(ErrorMessage(message="Authentication failed")))
                logger.warning(f"Auth failed from {remote}")
                return

            # Register node
            node_id = data.get("node_id", f"node-{id(ws)}")
            node = ConnectedNode(
                ws=ws,
                node_id=node_id,
                capabilities=data.get("capabilities", {}),
            )
            self.nodes[node_id] = node

            # Send welcome
            await ws.send(encode(WelcomeMessage(session_id=f"nova-{node_id}")))
            logger.info(f"Node connected: {node_id} (caps={node.capabilities})")

            # Start heartbeat
            heartbeat_task = asyncio.create_task(self._heartbeat(node))

            try:
                # Message loop
                async for raw in ws:
                    node.last_seen = time.time()

                    try:
                        data = decode(raw)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from {node_id}")
                        continue

                    if not validate_message(data, source="node"):
                        logger.warning(f"Invalid message from {node_id}: {data.get('type')}")
                        continue

                    # Spawn as task so message loop continues
                    # (critical: tool_result messages must be processed
                    #  while agent.chat() awaits in a transcription handler)
                    asyncio.create_task(self._handle_node_message(node, data))

            finally:
                heartbeat_task.cancel()

        except asyncio.TimeoutError:
            logger.warning(f"Connection from {remote} timed out during handshake")
        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            if node:
                self.nodes.pop(node.node_id, None)
                logger.info(f"Node disconnected: {node.node_id}")

    async def _handle_node_message(self, node: ConnectedNode, data: Dict[str, Any]):
        """Handle a message from a connected node."""
        msg_type = data["type"]

        if msg_type == "transcription":
            text = data.get("text", "").strip()
            if not text:
                return

            logger.info(f"Transcription from {node.node_id}: {text}")

            # Process through agent
            try:
                response = await self.agent.chat(text)
                await node.ws.send(encode(SpeakMessage(text=response)))
            except Exception as e:
                logger.error(f"Agent error: {e}")
                await node.ws.send(encode(SpeakMessage(
                    text="Sorry, I had trouble processing that."
                )))

        elif msg_type == "tool_result":
            request_id = data.get("request_id")
            result = data.get("result", "")
            future = self._pending_tools.get(request_id)
            if future and not future.done():
                future.set_result(result)
            else:
                logger.warning(f"Unexpected tool_result: {request_id}")

        elif msg_type == "vram_status":
            node.vram_status = {
                "free_gb": data.get("free_gb"),
                "used_gb": data.get("used_gb"),
                "total_gb": data.get("total_gb"),
                "models_loaded": data.get("models_loaded", []),
                "external_processes": data.get("external_processes", []),
            }
            logger.debug(f"VRAM status: {node.vram_status}")

        elif msg_type == "pong":
            pass  # Heartbeat response

    async def _heartbeat(self, node: ConnectedNode):
        """Send periodic pings to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(30)
                try:
                    await node.ws.send(encode(PingMessage()))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    async def start(self):
        """Start the WebSocket server."""
        logger.info(f"Starting Nova Server on ws://{self.config.host}:{self.config.port}")

        if not self.config.auth_token:
            logger.warning("No auth_token configured! Set one in config.yaml")

        # Check Pixel Bot availability
        if self.pixelbot.is_available():
            logger.info("Pixel Bot (OpenClaw) available locally")
        else:
            logger.warning("Pixel Bot (OpenClaw) not found! AI responses won't work")

        async with serve(
            self.handle_connection,
            self.config.host,
            self.config.port,
            ping_interval=None,  # We handle our own heartbeat
        ) as server:
            logger.info(f"Nova Server running on ws://{self.config.host}:{self.config.port}")
            await asyncio.Future()  # Run forever
