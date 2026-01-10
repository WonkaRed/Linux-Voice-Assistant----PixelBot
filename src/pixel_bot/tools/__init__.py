"""
Pixel Bot Tools - Tool arsenal for intelligent assistance.

Available tools:
- SystemStatsTool: Advanced system stats with filtering
- WebSearchTool: DuckDuckGo web search
- ExecuteCommandTool: Safe command execution
- SearchFilesTool: Find files by name/pattern
- ReadFileTool: Read file contents
- VolumeControlTool: Audio volume control (mute/unmute/set)
- MathCalculatorTool: Safe mathematical expression evaluation
"""
from .base_tool import BaseTool
from .registry import ToolRegistry
from .system_stats_tool import SystemStatsTool
from .web_search_tool import WebSearchTool
from .execute_command_tool import ExecuteCommandTool
from .file_tools import SearchFilesTool, ReadFileTool
from .volume_control_tool import VolumeControlTool
from .math_calculator_tool import MathCalculatorTool

__all__ = [
    'BaseTool',
    'ToolRegistry',
    'SystemStatsTool',
    'WebSearchTool',
    'ExecuteCommandTool',
    'SearchFilesTool',
    'ReadFileTool',
    'VolumeControlTool',
    'MathCalculatorTool',
]
