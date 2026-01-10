"""
Math Calculator Handler

Handles mathematical calculations using HARDCODED formulas and Python eval.
NEVER uses LLM for calculations (it's unreliable - tested at 60% accuracy!).

Commands:
- what's 5 times 8?
- calculate 15% of 200
- convert 50 fahrenheit to celsius
"""
import logging
import re
import ast
import operator
import math
from typing import Optional, Any

from .base import BaseHandler

logger = logging.getLogger(__name__)


class MathCalculatorHandler(BaseHandler):
    """
    Handles math calculations.

    CRITICAL: Never uses LLM for calculations!
    LLM test results: 60% accuracy with failures like 12-7=-6, 15*12=30

    Uses:
    - Hardcoded conversion formulas
    - Python's eval() with strict sandboxing
    - LLM only for formatting final answer
    """

    # Safe operators for eval
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    # Safe functions for eval
    SAFE_FUNCTIONS = {
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'sum': sum,
        'sqrt': math.sqrt,
        'pow': math.pow,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'pi': math.pi,
        'e': math.e,
    }

    # Conversion formulas (hardcoded for reliability)
    CONVERSIONS = {
        'fahrenheit_to_celsius': lambda f: (f - 32) * 5/9,
        'celsius_to_fahrenheit': lambda c: c * 9/5 + 32,
        'miles_to_km': lambda m: m * 1.60934,
        'km_to_miles': lambda km: km / 1.60934,
        'pounds_to_kg': lambda lb: lb * 0.453592,
        'kg_to_pounds': lambda kg: kg / 0.453592,
        'feet_to_meters': lambda ft: ft * 0.3048,
        'meters_to_feet': lambda m: m / 0.3048,
    }

    def handle(self, query: str, speak_response: bool = True) -> str:
        """
        Handle math calculation query.

        Args:
            query: User query
            speak_response: Whether to speak response

        Returns:
            str: Response text
        """
        try:
            query_lower = query.lower()

            # Check for conversions first (with or without "convert" keyword)
            # Detect patterns like "50 fahrenheit in celsius" or "convert 50 fahrenheit to celsius"
            conversion_patterns = [
                r'\bfahrenheit\b.*\b(to|in)\b.*\bcelsius\b',
                r'\bcelsius\b.*\b(to|in)\b.*\bfahrenheit\b',
                r'\bmiles?\b.*\b(to|in)\b.*\b(km|kilometers?)\b',
                r'\b(km|kilometers?)\b.*\b(to|in)\b.*\bmiles?\b',
                r'\b(pounds?|lbs?)\b.*\b(to|in)\b.*\b(kg|kilograms?)\b',
                r'\b(kg|kilograms?)\b.*\b(to|in)\b.*\b(pounds?|lbs?)\b',
                r'\bfeet\b.*\b(to|in)\b.*\bmeters?\b',
                r'\bmeters?\b.*\b(to|in)\b.*\bfeet\b',
            ]

            is_conversion = False
            if re.search(r'\bconvert\b', query_lower):
                is_conversion = True
            else:
                for pattern in conversion_patterns:
                    if re.search(pattern, query_lower):
                        is_conversion = True
                        break

            if is_conversion:
                response = self._handle_conversion(query_lower)
            elif re.search(r'(\bpercent\b|%)', query_lower) and re.search(r'\bof\b', query_lower):
                logger.info(f"Percentage pattern matched for query: {query_lower}")
                response = self._handle_percentage(query_lower)
            else:
                has_percent = bool(re.search(r'(\bpercent\b|%)', query_lower))
                has_of = bool(re.search(r'\bof\b', query_lower))
                logger.info(f"Percentage check failed - has_percent: {has_percent}, has_of: {has_of}")
                response = self._handle_calculation(query_lower)

            # Speak response
            self._speak(response, speak_response)

            return response

        except Exception as e:
            logger.error(f"Math calculation failed: {e}", exc_info=True)
            error_msg = "Sorry, I couldn't calculate that."
            self._speak(error_msg, speak_response)
            return error_msg

    def _handle_calculation(self, query: str) -> str:
        """
        Handle general calculation.

        Args:
            query: User query

        Returns:
            str: Response with answer
        """
        try:
            # Extract math expression from query
            expression = self._extract_expression(query)

            if not expression:
                return "I couldn't understand the calculation. Please try again."

            logger.info(f"Extracted expression: {expression}")

            # NEVER use LLM - calculate with safe eval
            result = self._safe_eval(expression)

            if result is None:
                return "I couldn't calculate that expression."

            logger.info(f"Calculation result: {result}")

            # Format the answer nicely (LLM is good at formatting)
            formatted = self._format_math_answer(expression, result)

            return formatted

        except Exception as e:
            logger.error(f"Calculation failed: {e}")
            return "I couldn't calculate that."

    def _handle_percentage(self, query: str) -> str:
        """
        Handle percentage calculations.

        Examples: "what's 15% of 200", "calculate 25 percent of 80"

        Args:
            query: User query

        Returns:
            str: Response with answer
        """
        try:
            # Extract percentage and base number
            # Pattern: "X% of Y" or "X percent of Y"
            match = re.search(r'(\d+\.?\d*)\s*%?\s*(?:percent)?\s*of\s*(\d+\.?\d*)', query)

            if not match:
                return "I couldn't understand the percentage calculation."

            percent = float(match.group(1))
            base = float(match.group(2))

            # Calculate (HARDCODED formula, not LLM!)
            result = (percent / 100) * base

            logger.info(f"Percentage calc: {percent}% of {base} = {result}")

            # Format response
            if result == int(result):
                return f"{int(percent)} percent of {int(base)} is {int(result)}"
            else:
                return f"{percent} percent of {base} is {result:.2f}"

        except Exception as e:
            logger.error(f"Percentage calculation failed: {e}")
            return "I couldn't calculate that percentage."

    def _handle_conversion(self, query: str) -> str:
        """
        Handle unit conversions.

        Examples: "convert 50 fahrenheit to celsius", "what is 50 fahrenheit in celsius"

        Args:
            query: User query

        Returns:
            str: Response with converted value
        """
        try:
            # Extract conversion type and value
            # Support both "to" and "in" keywords
            conversions = {
                r'(\d+\.?\d*)\s*(?:degrees?)?\s*fahrenheit\s*(?:to|in)\s*celsius': 'fahrenheit_to_celsius',
                r'(\d+\.?\d*)\s*(?:degrees?)?\s*celsius\s*(?:to|in)\s*fahrenheit': 'celsius_to_fahrenheit',
                r'(\d+\.?\d*)\s*miles?\s*(?:to|in)\s*(?:km|kilometers?)': 'miles_to_km',
                r'(\d+\.?\d*)\s*(?:km|kilometers?)\s*(?:to|in)\s*miles?': 'km_to_miles',
                r'(\d+\.?\d*)\s*(?:pounds?|lbs?)\s*(?:to|in)\s*(?:kg|kilograms?)': 'pounds_to_kg',
                r'(\d+\.?\d*)\s*(?:kg|kilograms?)\s*(?:to|in)\s*(?:pounds?|lbs?)': 'kg_to_pounds',
                r'(\d+\.?\d*)\s*feet\s*(?:to|in)\s*meters?': 'feet_to_meters',
                r'(\d+\.?\d*)\s*meters?\s*(?:to|in)\s*feet': 'meters_to_feet',
            }

            for pattern, conversion_type in conversions.items():
                match = re.search(pattern, query)
                if match:
                    value = float(match.group(1))
                    formula = self.CONVERSIONS[conversion_type]

                    # Use hardcoded formula (NOT LLM!)
                    result = formula(value)

                    logger.info(f"Conversion: {value} via {conversion_type} = {result}")

                    # Format response
                    return self._format_conversion_answer(value, result, conversion_type)

            return "I don't know that conversion. Try: fahrenheit/celsius, miles/km, pounds/kg"

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return "I couldn't convert that."

    def _extract_expression(self, query: str) -> Optional[str]:
        """
        Extract mathematical expression from natural language.

        Args:
            query: User query

        Returns:
            str: Mathematical expression or None
        """
        # Replace word operators with symbols
        replacements = {
            r'\bplus\b': '+',
            r'\bminus\b': '-',
            r'\btimes\b': '*',
            r'\bmultiplied by\b': '*',
            r'\bdivided by\b': '/',
            r'\bto the power of\b': '**',
            r'\bsquared\b': '**2',
            r'\bcubed\b': '**3',
        }

        expression = query
        for pattern, replacement in replacements.items():
            expression = re.sub(pattern, replacement, expression, flags=re.IGNORECASE)

        # Extract numbers and operators
        # Look for pattern: digit ... operators ... digit (must start with digit!)
        # This prevents matching just spaces or operators
        match = re.search(r'(\d+[\d\.\+\-\*/\(\)\s]*\d+|^\d+$)', expression)
        if match:
            expr = match.group(1).strip()
            # Clean up
            expr = re.sub(r'\s+', '', expr)  # Remove spaces
            if expr:  # Make sure we got something
                return expr

        # Fallback: try to find ANY number sequence with operators
        # Extract just the number-operator-number pattern
        match = re.search(r'(\d+(?:\.\d+)?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)', expression)
        if match:
            num1, op, num2 = match.groups()
            return f"{num1}{op}{num2}"

        return None

    def _safe_eval(self, expression: str) -> Optional[float]:
        """
        Safely evaluate mathematical expression.

        NEVER uses LLM! Uses Python's eval with strict sandboxing.

        Args:
            expression: Math expression (e.g., "5+3*2")

        Returns:
            float: Result or None if invalid
        """
        try:
            # Parse expression into AST
            tree = ast.parse(expression, mode='eval')

            # Evaluate AST with only safe operations
            result = self._eval_node(tree.body)

            return float(result)

        except Exception as e:
            logger.error(f"Safe eval failed: {e}")
            return None

    def _eval_node(self, node: ast.AST) -> Any:
        """
        Recursively evaluate AST node with only safe operations.

        Args:
            node: AST node

        Returns:
            Evaluated result
        """
        if isinstance(node, ast.Num):  # Number
            return node.n
        elif isinstance(node, ast.Constant):  # Python 3.8+ constant
            return node.value
        elif isinstance(node, ast.BinOp):  # Binary operation
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op = self.SAFE_OPERATORS.get(type(node.op))
            if op:
                return op(left, right)
            else:
                raise ValueError(f"Unsafe operator: {type(node.op)}")
        elif isinstance(node, ast.UnaryOp):  # Unary operation
            operand = self._eval_node(node.operand)
            op = self.SAFE_OPERATORS.get(type(node.op))
            if op:
                return op(operand)
            else:
                raise ValueError(f"Unsafe operator: {type(node.op)}")
        elif isinstance(node, ast.Call):  # Function call
            func_name = node.func.id if isinstance(node.func, ast.Name) else None
            func = self.SAFE_FUNCTIONS.get(func_name)
            if func:
                args = [self._eval_node(arg) for arg in node.args]
                return func(*args)
            else:
                raise ValueError(f"Unsafe function: {func_name}")
        else:
            raise ValueError(f"Unsafe node type: {type(node)}")

    def _format_math_answer(self, expression: str, result: float) -> str:
        """
        Format math answer naturally.

        Args:
            expression: Original expression
            result: Calculated result

        Returns:
            str: Natural language answer
        """
        # Clean up result
        if result == int(result):
            result_str = str(int(result))
        else:
            result_str = f"{result:.2f}"

        # Simple template (LLM can make this fancier if needed)
        return f"The answer is {result_str}"

    def _format_conversion_answer(self, from_val: float, to_val: float, conversion_type: str) -> str:
        """
        Format conversion answer.

        Args:
            from_val: Original value
            to_val: Converted value
            conversion_type: Type of conversion

        Returns:
            str: Natural language answer
        """
        # Clean up values
        if to_val == int(to_val):
            to_val_str = str(int(to_val))
        else:
            to_val_str = f"{to_val:.2f}"

        # Extract units from conversion type
        parts = conversion_type.split('_to_')
        from_unit = parts[0].replace('_', ' ')
        to_unit = parts[1].replace('_', ' ')

        return f"{int(from_val) if from_val == int(from_val) else from_val} {from_unit} is {to_val_str} {to_unit}"
