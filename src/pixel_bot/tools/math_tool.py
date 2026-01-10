"""
Math Tool - Safe mathematical expression evaluation.

Uses restricted eval with no builtins for safety.
"""
import logging
import ast
import operator

logger = logging.getLogger(__name__)


class MathTool:
    """
    Safely evaluate mathematical expressions.

    Supports: +, -, *, /, **, %, ()
    Does NOT support: variables, functions, imports, code execution
    """

    def __init__(self):
        """Initialize math tool with safe operators."""

        # Allowed operators
        self.operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
            ast.FloorDiv: operator.floordiv,
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }

    def evaluate(self, expression: str) -> str:
        """
        Safely evaluate a mathematical expression.

        Args:
            expression: Math expression (e.g., "2 + 2", "5 * (3 + 1)")

        Returns:
            Result as string or error message
        """
        if not expression or not expression.strip():
            return "ERROR: Empty expression"

        expression = expression.strip()

        # Convert ^ to ** for power operations (common mistake)
        expression = expression.replace('^', '**')

        logger.info(f"Math tool: Evaluating: {expression}")

        try:
            # Parse expression to AST
            tree = ast.parse(expression, mode='eval')

            # Evaluate using safe eval
            result = self._safe_eval(tree.body)

            # Format result
            if isinstance(result, float):
                # Round to avoid floating point precision issues
                if result.is_integer():
                    result = int(result)
                else:
                    result = round(result, 10)  # 10 decimal places

            logger.info(f"Math result: {result}")
            return str(result)

        except SyntaxError as e:
            logger.error(f"Math syntax error: {e}")
            return f"ERROR: Invalid math expression - {str(e)}"

        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.error(f"Math evaluation error: {e}")
            return f"ERROR: Math error - {str(e)}"

        except Exception as e:
            logger.error(f"Math tool failed: {e}")
            return f"ERROR: {str(e)}"

    def _safe_eval(self, node):
        """
        Recursively evaluate AST node safely.

        Only allows numbers, operators, and parentheses.
        """
        if isinstance(node, ast.Constant):  # Numbers (Python 3.8+)
            return node.value

        elif isinstance(node, ast.Num):  # Numbers (older Python)
            return node.n

        elif isinstance(node, ast.BinOp):  # Binary operations (x + y, x * y, etc.)
            left = self._safe_eval(node.left)
            right = self._safe_eval(node.right)
            op = self.operators.get(type(node.op))

            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")

            return op(left, right)

        elif isinstance(node, ast.UnaryOp):  # Unary operations (+x, -x)
            operand = self._safe_eval(node.operand)
            op = self.operators.get(type(node.op))

            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")

            return op(operand)

        else:
            raise ValueError(f"Unsupported expression type: {type(node).__name__}")

    def get_name(self) -> str:
        """Get tool name for function calling."""
        return "math"

    def get_description(self) -> str:
        """Get tool description for LLM prompting."""
        return """Evaluate mathematical expressions. Supports basic arithmetic: addition (+),
subtraction (-), multiplication (*), division (/), exponentiation (**), modulo (%), and parentheses.
Example: "2 + 2", "5 * (3 + 1)", "10 / 2", "2 ** 8" """

    def get_parameters_schema(self) -> dict:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The mathematical expression to evaluate (e.g., '2 + 2', '5 * (3 + 1)')"
                }
            },
            "required": ["expression"]
        }


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    tool = MathTool()

    print("=== Math Tool Safety Tests ===\n")

    # Test basic operations
    print("1. Basic Operations:")
    test_cases = [
        ("2 + 2", "4"),
        ("10 - 3", "7"),
        ("5 * 8", "40"),
        ("20 / 4", "5"),
        ("2 ** 8", "256"),
        ("10 % 3", "1"),
        ("10 // 3", "3"),  # Floor division
    ]

    for expr, expected in test_cases:
        result = tool.evaluate(expr)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {expr} = {result} (expected: {expected})")

    # Test complex expressions
    print("\n2. Complex Expressions:")
    complex_tests = [
        ("(2 + 3) * 4", "20"),
        ("2 + 3 * 4", "14"),  # Order of operations
        ("(10 + 5) / (2 + 1)", "5"),
        ("2 ** (3 + 1)", "16"),
        ("-5 + 10", "5"),  # Unary minus
    ]

    for expr, expected in complex_tests:
        result = tool.evaluate(expr)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {expr} = {result} (expected: {expected})")

    # Test safety (should fail)
    print("\n3. Safety Tests (should reject):")
    dangerous = [
        "import os",
        "os.system('ls')",
        "eval('2+2')",
        "__import__('os')",
        "lambda x: x",
        "[1, 2, 3]",  # Lists not allowed
        "{'a': 1}",  # Dicts not allowed
        "x = 5",  # Assignments not allowed
    ]

    for expr in dangerous:
        result = tool.evaluate(expr)
        status = "✓ BLOCKED" if result.startswith("ERROR:") else "✗ ALLOWED"
        print(f"  {status}: {expr}")

    # Test error handling
    print("\n4. Error Handling:")
    error_tests = [
        "10 / 0",  # Division by zero
        "2 +",  # Incomplete expression
        "",  # Empty expression
        "abc",  # Invalid characters
    ]

    for expr in error_tests:
        result = tool.evaluate(expr)
        status = "✓" if result.startswith("ERROR:") else "✗"
        print(f"  {status} Error handled: {expr[:20]}")
        print(f"      Result: {result[:60]}")
