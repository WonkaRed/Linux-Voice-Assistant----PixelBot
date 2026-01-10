"""
Base Tool Class - Foundation for all Pixel Bot tools.

Each tool defines:
- name: Unique identifier
- description: What it does (for LLM context)
- parameters: JSON schema for function calling
- execute: Main logic
"""
import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Base class for all tools."""

    def __init__(self):
        """Initialize tool."""
        self.name = self._get_name()
        self.description = self._get_description()
        self.parameters = self._get_parameters()

    @abstractmethod
    def _get_name(self) -> str:
        """
        Get tool name.

        Returns:
            str: Unique tool name
        """
        pass

    @abstractmethod
    def _get_description(self) -> str:
        """
        Get tool description.

        Returns:
            str: Description of what the tool does
        """
        pass

    @abstractmethod
    def _get_parameters(self) -> Dict[str, Any]:
        """
        Get tool parameters schema (JSON Schema format).

        Returns:
            dict: Parameters schema
        """
        pass

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        Execute the tool.

        Args:
            **kwargs: Tool parameters

        Returns:
            str: Tool result
        """
        pass

    def to_function_schema(self) -> Dict[str, Any]:
        """
        Convert tool to function calling schema.

        Returns:
            dict: Function schema for LLM
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
