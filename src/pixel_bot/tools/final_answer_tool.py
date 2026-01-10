"""
Final Answer Tool - Returns the final answer to the user.

This is a special "tool" that ends the agent loop and returns the response.
"""
import logging

logger = logging.getLogger(__name__)


class FinalAnswerTool:
    """
    Special tool for returning final answers to the user.

    This tool doesn't actually execute anything - it just signals
    that the agent has completed its mission and has an answer.
    """

    def execute(self, answer: str) -> str:
        """
        Return a final answer to the user.

        Args:
            answer: The final answer to return

        Returns:
            The answer (marked with a special prefix so agent_core knows to stop)
        """
        if not answer or not answer.strip():
            logger.warning("Empty final answer provided")
            return "FINAL_ANSWER:"

        answer = answer.strip()
        logger.info(f"Final answer: {answer}")

        # Return with special prefix so agent_core can detect it
        return f"FINAL_ANSWER:{answer}"

    def get_name(self) -> str:
        """Get tool name for function calling."""
        return "final_answer"

    def get_description(self) -> str:
        """Get tool description for LLM prompting."""
        return """Return your final answer to the user. Use this when you have all the information
needed to answer the user's question. The answer should be natural, concise (1-2 sentences),
and formatted for voice output."""

    def get_parameters_schema(self) -> dict:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "The final answer to return to the user (natural language, concise)"
                }
            },
            "required": ["answer"]
        }


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    tool = FinalAnswerTool()

    print("=== Final Answer Tool Test ===\n")

    # Test basic usage
    result = tool.execute("The answer is 42.")
    print(f"Result: {result}")
    print(f"Is final answer: {result.startswith('FINAL_ANSWER:')}")
    print(f"Answer text: {result.replace('FINAL_ANSWER:', '')}")

    # Test empty answer
    result = tool.execute("")
    print(f"\nEmpty result: {result}")
