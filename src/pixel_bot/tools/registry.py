"""
Tool Registry - Manages all available tools for Pixel Bot.

Responsibilities:
- Register all tools
- Provide tool schemas for function calling
- Execute tool calls
"""
import logging
from typing import Dict, List, Any, Optional

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all Pixel Bot tools."""

    def __init__(self):
        """Initialize tool registry."""
        self._tools: Dict[str, BaseTool] = {}
        logger.info("Tool registry initialized")

    def register_tool(self, tool: BaseTool):
        """
        Register a tool.

        Args:
            tool: Tool instance to register
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")

        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None
        """
        return self._tools.get(name)

    def get_all_tools(self) -> List[BaseTool]:
        """
        Get all registered tools.

        Returns:
            list: All tool instances
        """
        return list(self._tools.values())

    def get_function_schemas(self) -> List[Dict[str, Any]]:
        """
        Get function schemas for all tools (for LLM function calling).

        Returns:
            list: Function schemas
        """
        return [tool.to_function_schema() for tool in self._tools.values()]

    def execute_tool(self, tool_name: str, **kwargs) -> str:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of tool to execute
            **kwargs: Tool parameters

        Returns:
            str: Tool result

        Raises:
            ValueError: If tool not found
        """
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")

        logger.info(f"Executing tool '{tool_name}' with params: {kwargs}")

        try:
            result = tool.execute(**kwargs)
            logger.info(f"Tool '{tool_name}' completed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool '{tool_name}' failed: {e}", exc_info=True)
            raise

    def get_tool_count(self) -> int:
        """
        Get number of registered tools.

        Returns:
            int: Tool count
        """
        return len(self._tools)

    def __repr__(self) -> str:
        return f"<ToolRegistry: {self.get_tool_count()} tools>"
