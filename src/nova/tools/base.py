"""
Base Tool Class - Foundation for all Nova tools.

Each tool provides:
- name: Unique identifier
- description: What it does (for routing context)
- parameters: JSON schema for function calling
- execute: Main logic
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Abstract base class for all Nova tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for routing context."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """Parameter definitions (JSON Schema properties)."""
        pass

    @property
    def required_params(self) -> List[str]:
        """List of required parameter names."""
        return []

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        Execute the tool with given parameters.

        Args:
            **kwargs: Tool parameters

        Returns:
            str: Tool result or error message
        """
        pass

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
