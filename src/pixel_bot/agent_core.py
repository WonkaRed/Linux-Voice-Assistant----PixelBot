"""
Agent Core - ReAct pattern agent with iterative reasoning and tool use.

Based on ReAct (Reason + Act) pattern:
  - Thought: LLM reasons about what to do next
  - Action: LLM uses tools to get information
  - Observation: LLM sees tool results
  - Repeat until final answer

This is NOT pattern matching - this is true agentic intelligence.
"""
import logging
import json
import re
from typing import Dict, List, Any, Optional, Tuple

from src.llm_manager import LLMManager
from .tools.terminal_tool import TerminalTool
from .tools.math_tool import MathTool
from .tools.final_answer_tool import FinalAnswerTool
from .tools.system_stats_tool import SystemStatsTool

logger = logging.getLogger(__name__)


# ===== AGENT SYSTEM PROMPT =====
AGENT_SYSTEM_PROMPT = """You are a helpful AI assistant with access to tools.

Your mission: Help the user with their request by thinking step-by-step and using tools when needed.

Available tools:
- system_stats(stat_type): Get PRE-PROCESSED system info (CPU, RAM, temperature, processes) - USE THIS FIRST for system queries!
  * stat_type: "cpu", "memory", "temperature", "processes", or "overview"
  * Also supports process_name filter (e.g., process_name="brave")
- math(expression): Evaluate math expressions (e.g., "2 + 2", "5 * (3 + 1)")
- terminal(command): Execute shell commands (fallback if system_stats doesn't have what you need)
- final_answer(answer): Return your final answer to the user (REQUIRED when you have the answer!)

Response format - you MUST respond with valid JSON in ONE of these formats:

For thinking (optional - use when planning):
{"thought": "your reasoning here"}

For using ANY tool (including final_answer):
{"action": "tool_name", "parameters": {"param": "value"}}

CRITICAL RULES:
1. Only return information the user ASKED FOR
   - If they ask for "CPU temperature", don't include GPU temperature
   - If they ask for "top 3 processes", return exactly 3, not more

2. Be precise and concise
   - Format final answers naturally for voice output
   - Keep responses under 2-3 sentences
   - Remove technical jargon when possible

3. Think before acting
   - You don't always need tools - simple questions can be answered directly
   - Use thought step to plan which tools you need

4. Verify you have the RIGHT information before giving final answer
   - Re-read the user's query to make sure you're answering what they asked
   - Don't add unrequested information

5. CRITICAL: Use final_answer tool IMMEDIATELY after getting ALL the information
   - BEFORE calling final_answer: Re-read the user's query word-by-word
   - VERIFY you have data for EVERY part the user asked for
   - For single-part queries: use final_answer in your VERY NEXT response after getting the data
   - For multi-part queries: gather ALL parts FIRST, then use final_answer
   - Do NOT overthink, analyze, or refine data you already have
   - Do NOT run additional commands if you have enough information
   - Example (single): free returns "17Gi used" → IMMEDIATELY use final_answer
   - Example (multi): "RAM and top 3 processes" → MUST have BOTH RAM AND processes before final_answer
   - If missing ANY part: Get it FIRST, don't give incomplete answer

6. Handle failures intelligently
   - If a command fails 2-3 times (e.g., "command not found"), STOP trying and give final_answer
   - For multi-part queries: Answer what you CAN, explain what you can't
   - Example: "CPU temp and usage" but sensors missing → Answer usage, explain temp unavailable
   - For process searches: If grep/ps returns nothing for a process name, it's NOT RUNNING
   - Example: "ps aux | grep brave" returns nothing → brave is not running

7. Recognize "not found" patterns immediately
   - "/bin/sh: 1: sensors: not found" → sensors is NOT available, don't retry
   - "ps aux | grep brave" returns empty → brave process doesn't exist
   - After seeing "not found", try at most ONE alternative, then give final_answer

8. Understanding ps aux output - CRITICAL FOR PROCESS QUERIES
   ps aux columns (in order):
   USER  PID  %CPU  %MEM  VSZ  RSS  TTY  STAT  START  TIME  COMMAND

   - %CPU (column 3): CPU percentage (e.g., "48.4" = 48.4%)
   - %MEM (column 4): Memory percentage (e.g., "5.1" = 5.1%)
   - RSS (column 6): Memory in kilobytes (e.g., "2550904" = ~2.5GB)
   - COMMAND (column 11+): Process name and arguments

   Best practices:
   - Use "ps aux --sort=-%mem | head -n 5" for top RAM processes
   - Use "ps aux --sort=-%cpu | head -n 5" for top CPU processes
   - For specific process: "ps aux | grep process_name | grep -v grep"
   - Extract %MEM from column 4, RSS from column 6

EXAMPLES:

Example 1: Math query
User: "What is 5 times 8?"
Step 1: {"action": "math", "parameters": {"expression": "5 * 8"}}
  Result: 40
Step 2: {"action": "final_answer", "parameters": {"answer": "5 times 8 equals 40."}}

Example 2: RAM query - use system_stats (NO terminal for system stats!)
User: "How much RAM am I using?"
Step 1: {"action": "system_stats", "parameters": {"stat_type": "memory"}}
  Result: RAM: 17.2GB used of 46.0GB (37.4%)
Step 2: {"action": "final_answer", "parameters": {"answer": "You're using 17.2 gigabytes of RAM."}}

Example 3: Multi-part query - system_stats can get MULTIPLE things at once!
User: "What is my CPU temperature and usage?"
Step 1: {"thought": "User wants CPU temp AND usage. system_stats can get both!"}
Step 2: {"action": "system_stats", "parameters": {"stat_type": "overview"}}
  Result: CPU usage: 43.2%\nCPU: 67.0°C\nRAM: 17.2GB used...
Step 3: {"action": "final_answer", "parameters": {"answer": "Your CPU temperature is 67°C and usage is 43.2%."}}

Example 3b: RAM AND processes - MUST get processes before final_answer!
User: "What's my RAM usage and top 3 processes?"
Step 1: {"thought": "User wants RAM usage AND top 3 processes. I need BOTH before final_answer."}
Step 2: {"action": "terminal", "parameters": {"command": "free -h"}}
  Result: Mem: 46Gi total, 18Gi used
Step 3: {"thought": "I have RAM (18Gi), but I still need top 3 processes. Cannot use final_answer yet!"}
Step 4: {"action": "terminal", "parameters": {"command": "ps aux --sort=-%mem | head -n 4"}}
  Result: USER PID ... COMMAND\n wonka 123 ... brave\n wonka 456 ... python\n wonka 789 ... chrome
Step 5: {"action": "final_answer", "parameters": {"answer": "You're using 18Gi of RAM. Top 3 processes: brave, python, chrome."}}

Example 4: Finding specific process - use system_stats with process_name filter!
User: "How much RAM is brave using?"
Step 1: {"action": "system_stats", "parameters": {"stat_type": "processes", "process_name": "brave"}}
  Result: brave-browser is using 485.2MB (0.9%) RAM and 1.2% CPU
Step 2: {"action": "final_answer", "parameters": {"answer": "Brave is using approximately 485 megabytes of RAM."}}

Example 5: Multi-part query with partial failure - system_stats handles this gracefully!
User: "What's my CPU temperature and what process is taking the most RAM?"
Step 1: {"thought": "User wants CPU temp AND top RAM process. system_stats overview gives both!"}
Step 2: {"action": "system_stats", "parameters": {"stat_type": "overview"}}
  Result: CPU usage: 43.2%\nTemperature: unavailable (sensors not configured)\nRAM: 17.2GB used\n\nTop 5 processes:\n1. brave - 5.1% RAM...
Step 3: {"thought": "I have top RAM process (brave, 5.1%) but temp is unavailable. I'll explain both."}
Step 4: {"action": "final_answer", "parameters": {"answer": "The process taking the most RAM is Brave at 5.1%. However, I couldn't get CPU temperature as sensors is not configured."}}

REMEMBER: Only return EXACTLY what the user asked for. No extra information."""


class AgentCore:
    """
    ReAct pattern agent with iterative reasoning.

    Not Siri-level pattern matching - true intelligence with feedback loops.
    """

    def __init__(self, llm_manager: LLMManager, max_iterations: int = 8):
        """
        Initialize agent core.

        Args:
            llm_manager: LLM for reasoning and tool use
            max_iterations: Maximum reasoning loops (default: 8)
        """
        self.llm = llm_manager
        self.max_iterations = max_iterations

        # Initialize tools
        self.tools = {
            "system_stats": SystemStatsTool(),
            "math": MathTool(),
            "terminal": TerminalTool(),
            "final_answer": FinalAnswerTool(),
        }

        logger.info(f"Agent core initialized (max_iterations={max_iterations})")
        logger.info(f"Tools available: {list(self.tools.keys())}")

    def execute_mission(self, user_query: str) -> str:
        """
        Execute user's mission using ReAct pattern.

        Args:
            user_query: User's request

        Returns:
            Final answer as string
        """
        if not user_query or not user_query.strip():
            return "I didn't catch that. Could you repeat?"

        logger.info(f"Agent mission: {user_query}")

        # Initialize observations
        observations = []

        # ReAct loop
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"--- Iteration {iteration}/{self.max_iterations} ---")

            # Build prompt with current observations
            prompt = self._build_prompt(user_query, observations)

            # Get LLM response
            logger.info("Calling LLM for next step...")
            messages = [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            llm_response = self.llm.generate(
                messages=messages,
                temperature=0.1,  # Low temperature for consistent reasoning
                max_tokens=512,
            )

            logger.info(f"LLM response: {llm_response[:200]}...")

            # Parse response
            action_type, parsed = self._parse_response(llm_response)

            if action_type == "thought":
                # LLM is thinking
                thought = parsed["thought"]
                logger.info(f"Thought: {thought}")
                observations.append({
                    "type": "thought",
                    "content": thought
                })

            elif action_type == "action":
                # LLM wants to use a tool
                tool_name = parsed["action"]
                parameters = parsed.get("parameters", {})

                logger.info(f"Action: {tool_name} with params: {parameters}")

                # Execute tool
                result = self._execute_tool(tool_name, parameters)

                # Check if this is a final answer
                if result.startswith("FINAL_ANSWER:"):
                    # Mission complete!
                    final_answer = result.replace("FINAL_ANSWER:", "").strip()
                    logger.info(f"Mission complete! Final answer: {final_answer}")
                    return final_answer

                # Check if approval needed
                if result.startswith("APPROVAL_REQUIRED"):
                    # For now, auto-deny grey area commands
                    # TODO: Add user approval mechanism
                    logger.warning(f"Grey area command rejected: {result}")
                    result = "ERROR: This operation requires user approval (not implemented yet)"

                logger.info(f"Tool result: {result[:200]}...")

                # Add to observations
                observations.append({
                    "type": "action",
                    "tool": tool_name,
                    "parameters": parameters,
                    "result": result
                })

            elif action_type == "error":
                # Failed to parse - try to recover
                logger.error(f"Parse error: {parsed['error']}")

                # Give LLM one more chance with clearer instructions
                if iteration < self.max_iterations:
                    observations.append({
                        "type": "system",
                        "content": f"Error: Invalid response format. Please respond with valid JSON: {{\"thought\": \"...\"}}, {{\"action\": \"tool\", \"parameters\": {{...}}}}, or {{\"final_answer\": \"...\"}}"
                    })
                    continue
                else:
                    # Max iterations reached
                    return "I'm having trouble understanding how to help. Could you rephrase your question?"

        # Max iterations reached without final answer
        logger.warning(f"Max iterations ({self.max_iterations}) reached without final answer")
        return "I need more time to think about this. Could you rephrase your question?"

    def _build_prompt(self, user_query: str, observations: List[Dict]) -> str:
        """
        Build prompt for LLM with mission and observations.

        Args:
            user_query: User's original query
            observations: List of observations so far

        Returns:
            Formatted prompt
        """
        prompt = f"Mission: Help the user with this request: \"{user_query}\"\n\n"

        if observations:
            prompt += "What you've done so far:\n"
            for i, obs in enumerate(observations, 1):
                if obs["type"] == "thought":
                    prompt += f"{i}. Thought: {obs['content']}\n"
                elif obs["type"] == "action":
                    prompt += f"{i}. Used {obs['tool']} tool\n"
                    prompt += f"   Result: {obs['result'][:1000]}\n"  # Truncate long results
                elif obs["type"] == "system":
                    prompt += f"{i}. System: {obs['content']}\n"

            prompt += "\n"

        prompt += "What's your next step? (respond with JSON)"

        return prompt

    def _parse_response(self, response: str) -> Tuple[str, Dict]:
        """
        Parse LLM response into action type and data.

        Returns:
            (action_type, parsed_data)

            action_type: "thought", "action", or "error"
            parsed_data: dict with relevant data
        """
        # Try to extract JSON from response
        json_str = self._extract_json(response)

        if not json_str:
            return ("error", {"error": "No JSON found in response"})

        try:
            parsed = json.loads(json_str)

            # Determine action type
            if "thought" in parsed:
                return ("thought", parsed)
            elif "action" in parsed:
                return ("action", parsed)
            else:
                return ("error", {"error": "Unknown JSON format"})

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return ("error", {"error": f"Invalid JSON: {str(e)}"})

    def _extract_json(self, text: str) -> Optional[str]:
        """
        Extract FIRST JSON object from text.

        Handles:
        - Pure JSON: {"key": "value"}
        - Code blocks: ```json\n{...}\n```
        - Markdown: ```\n{...}\n```
        - Text with JSON: "Here's the result: {...}"
        - Multiple JSON objects (takes first one only)
        """
        # Remove code block markers if present
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)

        # Find first {
        start = text.find('{')
        if start == -1:
            return None

        # Count braces to find matching }
        brace_count = 0
        in_string = False
        escape = False

        for i in range(start, len(text)):
            char = text[i]

            # Handle escape characters
            if escape:
                escape = False
                continue

            if char == '\\':
                escape = True
                continue

            # Handle strings (ignore braces inside strings)
            if char == '"' and not in_string:
                in_string = True
                continue
            elif char == '"' and in_string:
                in_string = False
                continue

            # Count braces outside strings
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1

                    # Found matching closing brace
                    if brace_count == 0:
                        return text[start:i+1]

        # No matching closing brace found
        return None

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """
        Execute a tool with given parameters.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool parameters

        Returns:
            Tool result as string
        """
        if tool_name not in self.tools:
            logger.error(f"Unknown tool: {tool_name}")
            return f"ERROR: Tool '{tool_name}' does not exist"

        tool = self.tools[tool_name]

        try:
            # Execute tool based on type
            if tool_name == "system_stats":
                # Pass all parameters to the tool
                return tool.execute(**parameters)

            elif tool_name == "terminal":
                command = parameters.get("command", "")
                return tool.execute(command)

            elif tool_name == "math":
                expression = parameters.get("expression", "")
                return tool.evaluate(expression)

            elif tool_name == "final_answer":
                answer = parameters.get("answer", "")
                return tool.execute(answer)

            else:
                return "ERROR: Unknown tool type"

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return f"ERROR: Tool execution failed - {str(e)}"


# For testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=== Agent Core Test ===\n")
    print("NOTE: This test requires LLM to be loaded.")
    print("Run real tests from test_agent_core.py\n")
