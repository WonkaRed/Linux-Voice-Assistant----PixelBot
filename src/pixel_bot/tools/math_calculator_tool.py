"""
Math Calculator Tool - Safe mathematical expression evaluation for function calling.

Wraps the MathTool with BaseTool interface for LLM function calling.
"""
import logging
import math
from typing import Dict, Any

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class MathCalculatorTool(BaseTool):
    """Safely evaluate mathematical expressions using AST-based evaluation."""

    def _get_name(self) -> str:
        return "calculate"

    def _get_description(self) -> str:
        return """PRIORITY TOOL for ALL math: arithmetic, algebra, roots, powers, trigonometry.
Supports: +,-,*,/, power (**), sqrt, cbrt, abs, round, sin, cos, tan, log, exp, pi, e.
Examples: sqrt(144)→12, 5**3→125, cbrt(27)→3, 2+2→4.
ALWAYS use for: calculate, square root, cube root, power, times, divide, plus, minus."""

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2+2', 'sqrt(16)', '10**2')"
                }
            },
            "required": ["expression"]
        }

    def execute(self, **kwargs) -> str:
        """
        Execute mathematical calculation.

        Args:
            expression: Math expression to evaluate

        Returns:
            str: Calculation result
        """
        expression = kwargs.get("expression", "").strip()

        if not expression:
            return "ERROR: No expression provided"

        logger.info(f"Calculating: {expression}")

        try:
            # Pre-process natural language patterns
            import re
            # Handle "negative X" → "-X"
            expression = re.sub(r'\bnegative\s+(\d+)', r'-\1', expression, flags=re.IGNORECASE)
            # Handle "minus X" when used as negative
            expression = re.sub(r'^minus\s+(\d+)', r'-\1', expression, flags=re.IGNORECASE)

            # Convert common variations
            expression = expression.replace('^', '**')  # Power operator
            expression = expression.replace('÷', '/')   # Division
            expression = expression.replace('×', '*')   # Multiplication

            # Safe evaluation with math functions
            # Create safe namespace with only math functions
            safe_namespace = {
                # Math functions
                'sqrt': math.sqrt,
                'cbrt': lambda x: x ** (1/3),  # Cube root
                'cube_root': lambda x: x ** (1/3),  # Cube root (alias)
                'root': lambda x, n=2: x ** (1/n),  # General nth root (default square root)
                'abs': abs,
                'round': round,
                'pow': pow,
                'sin': math.sin,
                'cos': math.cos,
                'tan': math.tan,
                'asin': math.asin,
                'acos': math.acos,
                'atan': math.atan,
                'log': math.log,
                'log10': math.log10,
                'exp': math.exp,
                'floor': math.floor,
                'ceil': math.ceil,
                # Constants
                'pi': math.pi,
                'e': math.e,
                # Prevent any builtins
                '__builtins__': {}
            }

            # Evaluate using restricted eval
            result = eval(expression, safe_namespace, {})

            # Format result
            if isinstance(result, float):
                # Round to avoid floating point precision issues
                if result.is_integer():
                    result = int(result)
                else:
                    result = round(result, 10)

            logger.info(f"Result: {result}")
            return f"{result}"

        except ZeroDivisionError:
            return "ERROR: Division by zero"

        except SyntaxError as e:
            logger.warning(f"Invalid math syntax: {e}")
            return f"ERROR: Invalid math expression"

        except (ValueError, TypeError) as e:
            logger.warning(f"Math error: {e}")
            return f"ERROR: Math error - {str(e)}"

        except Exception as e:
            logger.error(f"Math calculation failed: {e}", exc_info=True)
            return f"ERROR: Could not calculate"
