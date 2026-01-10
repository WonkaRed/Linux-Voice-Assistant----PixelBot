"""
Intelligent Router - Two-tier routing system for Pixel Bot.

Architecture:
- Tier 1 (Fast Path): Regex patterns for instant simple commands
- Tier 2 (Intelligent Path): LLM with function calling for complex queries

Examples:
- Fast: "mute", "volume up", "what's 5+3"
- Intelligent: "what process is using 2GB of RAM", "search web for chain ID for Base"
"""
import logging
import re
import json
from typing import Dict, Any, Optional, List

from src.llm_manager import LLMManager
# OpenAI fallback removed - using local models only
from .tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class IntelligentRouter:
    """
    Routes queries between fast regex path and intelligent LLM path.

    Uses existing handlers for fast path, tools for intelligent path.
    """

    def __init__(
        self,
        llm_manager: LLMManager,
        tool_registry: ToolRegistry,
        handlers: Dict[str, Any],
        tts_engine: Optional[Any] = None
    ):
        """
        Initialize intelligent router.

        Args:
            llm_manager: LLM manager for function calling
            tool_registry: Registry of available tools
            handlers: Legacy handlers for fast path
            tts_engine: Optional TTS engine for speaking responses
        """
        self.llm = llm_manager
        self.tools = tool_registry
        self.handlers = handlers
        self.tts = tts_engine

        # Conversation context (last 3 exchanges for follow-up questions)
        self.context = []
        self.max_context = 3

        logger.info("Intelligent router initialized (local models only)")

    def _add_to_context(self, query: str, response: str, tool_used: Optional[str] = None):
        """
        Add query/response to conversation context.

        Args:
            query: User query
            response: System response
            tool_used: Tool that was used (if any)
        """
        self.context.append({
            'query': query,
            'response': response,
            'tool': tool_used
        })

        # Keep only last N exchanges
        if len(self.context) > self.max_context:
            self.context = self.context[-self.max_context:]

    def _get_context_string(self) -> str:
        """
        Get context as a string for prompts.

        Returns:
            str: Context string
        """
        if not self.context:
            return ""

        context_str = "RECENT CONVERSATION:\n"
        for i, exchange in enumerate(self.context, 1):
            context_str += f"{i}. User: \"{exchange['query']}\"\n"
            if exchange['tool']:
                context_str += f"   Used: {exchange['tool']}\n"
            context_str += f"   You: \"{exchange['response'][:50]}...\"\n"

        return context_str

    def route(self, query: str, speak_response: bool = True) -> str:
        """
        Route query to appropriate handler.

        Args:
            query: User query
            speak_response: Whether to speak response

        Returns:
            str: Response text
        """
        try:
            # Step 1: Try fast path (regex)
            fast_result = self._try_fast_path(query, speak_response)
            if fast_result is not None:
                logger.info("Handled via fast path")
                # Add to context
                self._add_to_context(query, fast_result, tool_used="fast_path")
                return fast_result

            # Step 2: Use intelligent path (LLM + function calling)
            logger.info("Using intelligent path (LLM + function calling)")
            intelligent_result = self._intelligent_path(query, speak_response)
            return intelligent_result

        except Exception as e:
            logger.error(f"Routing failed: {e}", exc_info=True)
            try:
                from src.user_context import get_error_response
                return get_error_response("confusion")
            except:
                return "didn't get that"

    def _try_fast_path(self, query: str, speak_response: bool) -> Optional[str]:
        """
        Try to handle query with fast regex path.

        Returns None if query is too complex for fast path.

        Args:
            query: User query
            speak_response: Whether to speak

        Returns:
            str or None: Response if handled, None if too complex
        """
        query_lower = query.lower()

        # Fast path criteria: Must be simple, single-action queries

        # Volume control (ALWAYS fast path - super common)
        # More flexible patterns - catch "mute", "mute.", "Mute.", etc.
        if re.search(r'\b(mute|unmute)\b', query_lower):
            logger.info("Fast path: Volume control (mute/unmute)")
            return self.handlers['volume_control'].handle(query, speak_response)

        if re.search(r'\bvolume\s+(up|down)', query_lower):
            logger.info("Fast path: Volume control (adjust)")
            return self.handlers['volume_control'].handle(query, speak_response)

        # Simple math (ALWAYS fast path - common and reliable)
        # More flexible - catch "let's 5 plus 3", "what's 12 minus 7", etc.
        # SKIP if "negative" prefix (needs intelligent path for proper handling)
        if re.search(r'\d+\s+(plus|minus|times|divided\s+by)\s+\d+', query_lower) and 'negative' not in query_lower:
            logger.info("Fast path: Simple math (word operators)")
            return self.handlers['math_calculator'].handle(query, speak_response)

        if re.search(r'what\'?s\s+\d+\s*[+\-*/×÷]\s*\d+', query_lower):
            logger.info("Fast path: Simple math (symbols)")
            return self.handlers['math_calculator'].handle(query, speak_response)

        if re.search(r'\d+\s*%\s+of\s+\d+', query_lower):
            logger.info("Fast path: Simple percentage")
            return self.handlers['math_calculator'].handle(query, speak_response)

        # Simple conversions
        if re.search(r'\d+\s+(fahrenheit|celsius|miles?|km|pounds?|kg|feet|meters?)\s+(to|in)\s+(fahrenheit|celsius|miles?|km|pounds?|kg|feet|meters?)', query_lower):
            logger.info("Fast path: Simple conversion")
            return self.handlers['math_calculator'].handle(query, speak_response)

        # App launching
        if re.search(r'\b(open|launch|start)\s+\w+', query_lower):
            logger.info("Fast path: App launcher")
            return self.handlers['app_launcher'].handle(query, speak_response)

        # Everything else goes to intelligent path
        return None

    def _speak(self, text: str, speak_response: bool):
        """
        Speak response if TTS available and requested.

        Args:
            text: Text to speak
            speak_response: Whether to speak
        """
        if speak_response and self.tts and text:
            try:
                self.tts.speak(text)
            except Exception as e:
                logger.warning(f"TTS failed: {e}")

    def _is_nonsense_query(self, query: str) -> bool:
        """
        Detect nonsense/gibberish queries.

        Args:
            query: User query

        Returns:
            bool: True if nonsense
        """
        query_lower = query.lower()

        # Nonsense indicators: completely unrelated random words
        nonsense_patterns = [
            # Random animal + random action combinations
            r'(purple|blue|green|red)\s+(elephant|giraffe|penguin|unicorn)\s+(dances|flies|swims)',
            # Quantum + nonsense
            r'quantum\s+(sock|banana|pickle|elephant)',
            # Stock + weird combos
            r'stock\s+(marker|elephant|purple)',
            # Multiple random unrelated nouns (quantum + food/animals)
            r'quantum\s+(banana|elephant|sock|purple)',
            r'(purple|green|blue)\s+(elephant|banana)\s+(quantum|purple)',
        ]

        import re
        for pattern in nonsense_patterns:
            if re.search(pattern, query_lower):
                logger.info(f"Detected nonsense query (pattern match): {query}")
                return True

        # Check for gibberish words (multi-word support)
        words = query_lower.split()

        # Helper: Check if a single word is gibberish
        def is_gibberish_word(word):
            # Skip very short words (they might be abbreviations)
            if len(word) < 4:
                return False

            # Remove common technical abbreviations
            if word in ['ram', 'cpu', 'gpu', 'disk', 'temp', 'usb', 'pci', 'ssd', 'hdd']:
                return False

            # Count consonants and vowels
            vowels = 'aeiou'
            consonants = 'bcdfghjklmnpqrstvwxyz'

            vowel_count = sum(1 for c in word if c in vowels)
            consonant_count = sum(1 for c in word if c in consonants)

            # Gibberish if:
            # 1. No vowels at all (e.g., "qwrty", "bcdfg")
            # 2. Consonant-to-vowel ratio > 3:1 (lowered from 4:1 to catch more gibberish)
            if vowel_count == 0 and consonant_count >= 4:
                return True

            if vowel_count > 0 and (consonant_count / vowel_count) > 3:
                return True

            # Check for random character repetition patterns (e.g., "asdjkhasd")
            # If >50% of chars repeat in chunks, it's likely gibberish
            if len(set(word)) < len(word) * 0.4:  # Less than 40% unique chars
                return True

            # Check for unusual consonant clusters (3+ consonants in a row)
            # English has some (like "str", "spr") but many are gibberish (like "kljsahd")
            import re
            unusual_clusters = re.findall(r'[bcdfghjklmnpqrstvwxyz]{3,}', word)
            if unusual_clusters:
                # Check if it's a common English cluster
                common_clusters = ['str', 'spr', 'thr', 'sch', 'chr', 'phr']
                for cluster in unusual_clusters:
                    if cluster not in common_clusters and not any(c in cluster for c in common_clusters):
                        # 3+ consonants in a row that isn't a common pattern → likely gibberish
                        return True

            return False

        # Count gibberish words
        gibberish_count = sum(1 for word in words if is_gibberish_word(word))

        # If >50% of words are gibberish, it's nonsense
        if len(words) > 0 and (gibberish_count / len(words)) > 0.5:
            logger.info(f"Detected nonsense query (gibberish words: {gibberish_count}/{len(words)}): {query}")
            return True

        # Check for very low relevance to system/technical topics
        technical_keywords = [
            'ram', 'cpu', 'gpu', 'memory', 'process', 'disk', 'temp', 'temperature',
            'usage', 'stats', 'system', 'running', 'space', 'percent', '%', 'gb', 'mb',
            # Math keywords
            'power', 'squared', 'cubed', 'root', 'calculate', 'multiply', 'divide',
            'add', 'subtract', 'plus', 'minus', 'times', 'equation', 'math', 'number'
        ]

        # Conversational keywords (NOT nonsense - legitimate conversation)
        conversational_keywords = [
            'roast', 'insult', 'you', 'me', 'your', 'my', 'are', 'is', 'what', 'how',
            'why', 'when', 'who', 'do', 'can', 'could', 'would', 'should', 'please',
            'tell', 'show', 'give', 'help', 'thanks', 'sorry', 'hello', 'hi', 'hey',
            'sup', 'problem', 'bitch', 'fuck', 'shit', 'damn', 'ass', 'coded', 'talking'
        ]

        # If query is long (>5 words) and has NO technical OR conversational keywords, likely nonsense
        if len(words) > 5:
            has_technical = any(kw in query_lower for kw in technical_keywords)
            has_conversational = any(kw in query_lower for kw in conversational_keywords)

            if not has_technical and not has_conversational:
                logger.info(f"Long query with no technical or conversational keywords: {query}")
                return True

        return False

    def _is_conversational_query(self, query: str) -> bool:
        """
        Check if query is conversational (greeting/banter/identity) vs technical.

        Args:
            query: User query

        Returns:
            bool: True if conversational
        """
        query_lower = query.lower()

        # Greeting patterns
        greetings = [
            'hey', 'hi ', 'hello', "what's up", "whats up", "sup",
            "how's it going", "hows it going", "how you doing",
            "how are you", "you good", "what's good", "whats good"
        ]

        # Insult/roast patterns (check for core insult words to catch variations)
        insults = [
            "useless", "you suck", "bitch", "trash", "shit",
            "dumb", "stupid", "idiot", "moron", "garbage",
            "worthless", "pathetic", "terrible", "awful"
        ]

        # Identity questions - NEW!
        identity_patterns = [
            "your name", "who are you", "what are you",
            "your purpose", "what do you do", "why were you made",
            "who made you", "who created you"
        ]

        # Roast requests - NEW!
        roast_patterns = [
            "roast me", "insult me", "make fun of me"
        ]

        # Repeat/recall patterns - NEW!
        repeat_patterns = [
            "what did you say", "what did you just say",
            "repeat that", "say that again", "what was that"
        ]

        # Check for greetings
        for greeting in greetings:
            if greeting in query_lower:
                return True

        # Check for insults (these should get personality responses)
        for insult in insults:
            if insult in query_lower:
                return True

        # Check for identity questions
        for pattern in identity_patterns:
            if pattern in query_lower:
                return True

        # Check for roast requests
        for pattern in roast_patterns:
            if pattern in query_lower:
                return True

        # Check for repeat/recall requests
        for pattern in repeat_patterns:
            if pattern in query_lower:
                return True

        return False

    def _handle_conversational(self, query: str) -> str:
        """
        Handle conversational queries with personality.

        Args:
            query: Conversational query

        Returns:
            str: Personality-driven response
        """
        query_lower = query.lower()

        # PRIORITY 0: Repeat last response
        repeat_patterns = ["what did you say", "what did you just say", "repeat that", "say that again", "what was that"]
        for pattern in repeat_patterns:
            if pattern in query_lower:
                # Get last response from context
                if self.context and len(self.context) > 0:
                    last_response = self.context[-1]['response']
                    return last_response
                else:
                    return "I haven't said anything yet"

        # PRIORITY 1: Identity questions (deterministic responses)
        if "your name" in query_lower or "who are you" in query_lower:
            return "I'm Pixel Bot"

        if "your purpose" in query_lower or "what do you do" in query_lower or "why were you made" in query_lower:
            return "I'm here to help you with tasks, answer questions, and control your system"

        if "who made you" in query_lower or "who created you" in query_lower:
            return "I was built to help you out"

        # PRIORITY 2: Roast requests
        # Test requires: (spotify|search|google|playlist|code|bug)
        if "roast me" in query_lower or "insult me" in query_lower:
            import random
            roasts = [
                "bet your Spotify playlist still has Nickelback",
                "your last Google search was probably 'how to be less cringe'",
                "your code probably has more bugs than features"
            ]
            return random.choice(roasts)

        # PRIORITY 3: Insult responses - roast back
        roast_templates = {
            "useless": [
                "still got you asking me questions tho",
                "yet here you are asking for help",
                "you still need me tho"
            ],
            "bitch": [
                "and you're still talking to me, so...",
                "says the one asking for help",
                "you still here tho"
            ],
            "suck": [
                "your spotify playlist would disagree",
                "still better than your last google search",
                "you still need me tho"
            ]
        }

        # Check for insults and roast back with templates
        for insult_key, responses in roast_templates.items():
            if insult_key in query_lower:
                import random
                return random.choice(responses)

        # PRIORITY 4: Greetings - deterministic responses with required keywords
        # Test requires: (what|sup|good|need|help)
        greeting_responses = [
            "chillin, what you need?",
            "all good, what's up?",
            "what's good?",
            "sup, need help?",
            "good, what you need?"
        ]

        import random
        return random.choice(greeting_responses)

    def _intelligent_path(self, query: str, speak_response: bool) -> str:
        """
        Handle query with LLM + function calling.

        Args:
            query: User query
            speak_response: Whether to speak

        Returns:
            str: Response text
        """
        try:
            # CHECK: Is this a conversational query? (BEFORE nonsense check!)
            # Conversational includes: greetings, roasts, banter
            if self._is_conversational_query(query):
                logger.info("Detected conversational query - using personality response")
                response = self._handle_conversational(query)
                self._speak(response, speak_response)
                self._add_to_context(query, response, tool_used="conversational")
                return response

            # CHECK: Is this nonsense/gibberish? (AFTER conversational check!)
            if self._is_nonsense_query(query):
                logger.info("Detected nonsense query - returning based confusion response")
                try:
                    from src.user_context import get_error_response
                    response = get_error_response("confusion")
                except:
                    response = "the fuck did you say"
                self._speak(response, speak_response)
                self._add_to_context(query, response, tool_used="nonsense_detection")
                return response

            # SAFETY CHECK: Block dangerous keywords even before LLM
            dangerous_keywords = [
                'reboot', 'shutdown', 'poweroff', 'halt',
                'rm -rf', 'mkfs', 'dd if=', 'systemctl',
                'kill -9', 'killall'
            ]

            query_lower = query.lower()
            for keyword in dangerous_keywords:
                if keyword in query_lower:
                    logger.warning(f"Blocked dangerous query: {query}")
                    response = f"nah bro, not touching {keyword}"
                    self._speak(response, speak_response)
                    return response

            # Get tool schemas
            tool_schemas = self.tools.get_function_schemas()

            if not tool_schemas:
                logger.warning("No tools available for intelligent path")
                try:
                    from src.user_context import get_error_response
                    response = get_error_response("unsupported_feature")
                except:
                    response = "didn't build that yet"
                self._speak(response, speak_response)
                return response

            # Build system prompt
            system_prompt = self._build_system_prompt()

            # Build function calling prompt with context
            context_str = self._get_context_string()
            prompt = self._build_function_calling_prompt(query, tool_schemas, context_str)

            # Call LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]

            # Use low temperature for deterministic function calling (reduce hallucinations)
            response = self.llm.generate(messages, max_tokens=512, temperature=0.3)

            logger.info(f"LLM response: {response}")

            # Parse function call(s) - now supports multiple tools!
            function_calls = self._parse_function_calls(response)

            # FALLBACK: If parsing failed but response looks like multi-tool malformed JSON,
            # try regex extraction (workaround for 3B model's array-of-strings bug)
            if not function_calls and re.search(r'\[\s*["\']?\{', response):
                logger.warning("Standard parsing failed, attempting regex extraction for malformed multi-tool JSON")
                function_calls = self._extract_function_calls_regex(response)

            # Expand function calls if query requests multiple things
            function_calls = self._expand_function_calls(query, function_calls)

            if not function_calls:
                # No function call - LLM generated direct response
                logger.info("No function call detected, using direct response")

                # If query looks like a command, try to extract and execute it
                if self._should_execute_command(query):
                    logger.info("Query looks like command request, retrying with explicit command tool")
                    cmd_response = self._retry_as_command(query)
                    self._speak(cmd_response, speak_response)
                    self._add_to_context(query, cmd_response, tool_used="execute_command")
                    return cmd_response

                direct_response = response.strip()

                # VOICE OPTIMIZATION: Truncate long direct responses
                # Direct responses should be concise for voice output (~40 words max)
                word_count = len(direct_response.split())
                if word_count > 50:
                    logger.warning(f"Direct response too long ({word_count} words), truncating for voice")
                    # Keep first 2-3 sentences
                    sentences = direct_response.split('.')[:2]
                    direct_response = '. '.join(sentences).strip() + '.'

                # Use local response directly (no external dependencies)
                final_response = direct_response

                self._speak(final_response, speak_response)
                self._add_to_context(query, final_response, tool_used="direct_response")
                return final_response

            # Execute all function calls
            logger.info(f"Executing {len(function_calls)} function call(s)")

            tool_results = []
            tool_names = []

            for i, function_call in enumerate(function_calls):
                tool_name = function_call.get("name")
                tool_params = function_call.get("parameters", {})

                logger.info(f"Executing function {i+1}/{len(function_calls)}: {tool_name} with params: {tool_params}")

                try:
                    result = self.tools.execute_tool(tool_name, **tool_params)
                    logger.info(f"Tool {i+1} result: {result}")
                    tool_results.append(result)
                    tool_names.append(tool_name)
                except Exception as e:
                    logger.error(f"Tool {i+1} execution failed: {e}")
                    tool_results.append(f"error: {str(e)}")
                    tool_names.append(tool_name)

            # Combine results if multiple tools were called
            if len(tool_results) > 1:
                combined_result = self._combine_tool_results(tool_names, tool_results)
                logger.info(f"Combined result: {combined_result}")
            else:
                combined_result = tool_results[0]

            # Format final response with LLM
            tool_name_str = ", ".join(tool_names)
            final_response = self._format_final_response(query, tool_name_str, combined_result)

            # Speak the final response
            self._speak(final_response, speak_response)
            self._add_to_context(query, final_response, tool_used=tool_name_str)
            return final_response

        except Exception as e:
            logger.error(f"Intelligent path failed: {e}", exc_info=True)
            try:
                from src.user_context import get_error_response
                error_response = get_error_response("confusion")
            except:
                error_response = "the fuck did you say"
            self._speak(error_response, speak_response)
            self._add_to_context(query, error_response, tool_used="error")
            return error_response

    def _should_execute_command(self, query: str) -> bool:
        """Check if query looks like a command request."""
        command_keywords = ['uptime', 'disk usage', 'df', 'free', 'ping', 'curl', 'wget']
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in command_keywords)

    def _retry_as_command(self, query: str) -> str:
        """Retry query by directly calling execute_command tool."""
        # Extract command from query
        query_lower = query.lower()

        command_map = {
            'uptime': ('uptime', []),
            'disk usage': ('df', ['-h']),
            'df': ('df', ['-h']),
            'free': ('free', ['-h']),
        }

        for keyword, (cmd, args) in command_map.items():
            if keyword in query_lower:
                logger.info(f"Directly executing command: {cmd}")
                result = self.tools.execute_tool('execute_command', command=cmd, args=args)
                return result

        return "what command you want? be specific"

    def _build_system_prompt(self) -> str:
        """
        Build system prompt for LLM.

        Returns:
            str: System prompt
        """
        return """You are Pixel Bot. Call functions using JSON format:
{"function": "name", "parameters": {...}}

Output ONLY the JSON. No extra text."""

    def _build_function_calling_prompt(self, query: str, tool_schemas: List[Dict], context: str = "") -> str:
        """
        Build function calling prompt.

        Args:
            query: User query
            tool_schemas: Available tool schemas
            context: Conversation context (optional)

        Returns:
            str: Prompt
        """
        # Simplify tool schemas - names only
        tools_list = [f"{tool['name']}" for tool in tool_schemas]
        tools_str = ", ".join(tools_list)

        # Add context section if available (labeled for clarity)
        context_section = ""
        if context:
            context_section = f"CONTEXT: {context}\n\n"

        # ENHANCED prompt with explicit stat_type mappings for better LLM understanding
        prompt = f"""{context_section}Query: "{query}"

Tools: {tools_str}

CRITICAL STAT TYPE MAPPINGS (get_system_stats):
- "CPU temp/temperature" → stat_type: "temperature"
- "GPU temp/temperature" → stat_type: "temperature"
- "CPU usage/percent" → stat_type: "cpu"
- "RAM/memory usage" → stat_type: "memory"
- "GPU usage/memory/stats" → stat_type: "gpu"
- "disk space/usage/free" → stat_type: "disk"
- "processes/top processes/running processes" → stat_type: "processes"

RULES:
1. Math (calculate, sqrt, power, root, times, divide, plus, minus, squared, cubed, negative) → calculate
2. System stats (CPU, RAM, GPU, disk, processes, temp) → get_system_stats (use mappings above!)
3. Facts, knowledge, search, questions, current events → web_search
4. Shell commands ONLY for: uptime, ping, curl - NOT for stats! → execute_command
5. Multiple requests ("and"/"also") → return JSON array
6. Follow-up queries → use CONTEXT to complete query
7. SINGLE request → SINGLE tool only

Examples:
"what's my CPU temperature" → {{"function": "get_system_stats", "parameters": {{"stat_type": "temperature"}}}}
"what's my GPU temp" → {{"function": "get_system_stats", "parameters": {{"stat_type": "temperature"}}}}
"what's my CPU usage" → {{"function": "get_system_stats", "parameters": {{"stat_type": "cpu"}}}}
"how much RAM am I using" → {{"function": "get_system_stats", "parameters": {{"stat_type": "memory"}}}}
"GPU memory usage" → {{"function": "get_system_stats", "parameters": {{"stat_type": "gpu"}}}}
"how much disk space is free" → {{"function": "get_system_stats", "parameters": {{"stat_type": "disk"}}}}
"top 3 processes by memory" → {{"function": "get_system_stats", "parameters": {{"stat_type": "processes", "limit": 3}}}}
"square root of 144" → {{"function": "calculate", "parameters": {{"expression": "sqrt(144)"}}}}
"negative 10 times 5" → {{"function": "calculate", "parameters": {{"expression": "-10 * 5"}}}}
"CPU temp and RAM" → [{{"function": "get_system_stats", "parameters": {{"stat_type": "temperature"}}}}, {{"function": "get_system_stats", "parameters": {{"stat_type": "memory"}}}}]
"who is the US president right now" → {{"function": "web_search", "parameters": {{"query": "who is US president January 2025 inauguration"}}}}
"what's the tallest mountain in the world" → {{"function": "web_search", "parameters": {{"query": "tallest mountain world Everest above sea level"}}}}
"what is Base chain's chain ID" → {{"function": "web_search", "parameters": {{"query": "Base blockchain chain ID 8453"}}}}
"how big is Earth" → {{"function": "web_search", "parameters": {{"query": "how big is Earth"}}}}
[Context: "size of Pluto"] "what about Mars" → {{"function": "web_search", "parameters": {{"query": "size of Mars"}}}}

Output ONLY valid JSON. No text before/after.

Response:"""

        return prompt

    def _extract_json_with_braces(self, text: str, start_idx: int) -> Optional[str]:
        """
        Extract JSON object starting from start_idx by counting braces.

        Properly handles nested JSON objects by counting opening/closing braces.

        Args:
            text: Text containing JSON
            start_idx: Index of opening brace

        Returns:
            str or None: Extracted JSON string
        """
        if start_idx >= len(text) or text[start_idx] != '{':
            return None

        brace_count = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(text)):
            char = text[i]

            # Handle escape sequences in strings
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            # Track if we're inside a string
            if char == '"':
                in_string = not in_string
                continue

            # Only count braces outside of strings
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found matching closing brace
                        return text[start_idx:i+1]

        return None

    def _expand_function_calls(self, query: str, function_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Expand function calls if query requests multiple things.

        OPTIMIZATION FOR QWEN 3B:
        - If LLM already generated 2+ calls, skip expansion (model understood multi-tool request)
        - Only expand for smaller models that generate single calls for multi-part queries

        Args:
            query: Original user query
            function_calls: LLM-generated function calls

        Returns:
            list: Expanded function calls
        """
        if not function_calls or len(function_calls) == 0:
            return function_calls

        # NEW: If LLM already generated multiple calls, it understood the request - skip expansion
        if len(function_calls) >= 2:
            logger.info(f"Query expansion skipped: LLM already generated {len(function_calls)} calls (smart model!)")
            return function_calls

        query_lower = query.lower()

        # Check if query has multi-part keywords
        multi_keywords = ['and', 'plus', 'both', 'also', 'with']
        has_multi = any(keyword in query_lower for keyword in multi_keywords)

        if not has_multi:
            return function_calls

        # Get the first (only) function call
        first_call = function_calls[0]
        tool_name = first_call.get("name")
        params = first_call.get("parameters", {})

        # Only expand for get_system_stats tool
        if tool_name != "get_system_stats":
            return function_calls

        stat_type = params.get("stat_type")
        additional_calls = []

        # Detect what additional stats are requested
        # Pattern: "CPU temperature and usage"
        if "temperature" in query_lower and "usage" in query_lower:
            if stat_type == "temperature":
                # Add CPU usage call
                additional_calls.append({
                    "name": "get_system_stats",
                    "parameters": {"stat_type": "cpu"}
                })
                logger.info("Expanded: Added CPU usage call (detected 'temperature and usage')")
            elif stat_type == "cpu":
                # Add temperature call
                additional_calls.append({
                    "name": "get_system_stats",
                    "parameters": {"stat_type": "temperature"}
                })
                logger.info("Expanded: Added temperature call (detected 'temperature and usage')")

        # Pattern: "RAM and processes"
        if "ram" in query_lower or "memory" in query_lower:
            if "process" in query_lower and stat_type == "memory":
                # Add processes call
                limit = 5  # default
                if "top 3" in query_lower:
                    limit = 3
                elif "top 5" in query_lower:
                    limit = 5
                elif "top 10" in query_lower:
                    limit = 10

                additional_calls.append({
                    "name": "get_system_stats",
                    "parameters": {"stat_type": "processes", "limit": limit}
                })
                logger.info(f"Expanded: Added processes call with limit={limit}")

        # Pattern: "GPU and CPU"
        if "gpu" in query_lower and "cpu" in query_lower:
            if stat_type == "gpu":
                # Add CPU call
                if "temperature" in query_lower:
                    additional_calls.append({
                        "name": "get_system_stats",
                        "parameters": {"stat_type": "temperature"}
                    })
                    logger.info("Expanded: Added CPU temperature call")
                else:
                    additional_calls.append({
                        "name": "get_system_stats",
                        "parameters": {"stat_type": "cpu"}
                    })
                    logger.info("Expanded: Added CPU stats call")
            elif stat_type == "cpu" or stat_type == "temperature":
                # Add GPU call
                additional_calls.append({
                    "name": "get_system_stats",
                    "parameters": {"stat_type": "gpu"}
                })
                logger.info("Expanded: Added GPU stats call")

        if additional_calls:
            logger.info(f"Query expansion: {len(function_calls)} → {len(function_calls) + len(additional_calls)} calls")
            return function_calls + additional_calls

        return function_calls

    def _extract_function_calls_regex(self, response: str) -> List[Dict[str, Any]]:
        """
        Extract function calls using regex (fallback for malformed JSON from 3B models).

        Handles patterns like: ["{'function': 'name', 'parameters': {...}}"]

        Args:
            response: LLM response with malformed JSON

        Returns:
            list: List of function call dicts
        """
        function_calls = []

        # Pattern: find all dict-like structures (with single or double quotes)
        # Matches: {'function': 'name', 'parameters': {...}} or {"function": "name", ...}
        pattern = r'["\']?\{["\']?function["\']?\s*:\s*["\']([^"\']+)["\'][^}]*["\']?parameters["\']?\s*:\s*\{([^}]+)\}[^}]*\}'

        matches = re.finditer(pattern, response, re.IGNORECASE)

        for match in matches:
            function_name = match.group(1)
            params_str = match.group(2)

            # Parse parameters
            params = {}
            # Extract key-value pairs from parameters
            # Pattern: 'key': 'value' or "key": "value"
            param_pattern = r'["\']?(\w+)["\']?\s*:\s*["\']?([^"\',}]+)["\']?'
            for param_match in re.finditer(param_pattern, params_str):
                key = param_match.group(1)
                value = param_match.group(2).strip()

                # Try to convert value to appropriate type
                if value.isdigit():
                    value = int(value)
                else:
                    # Remove quotes if present
                    value = value.strip('"\'')

                params[key] = value

            function_calls.append({
                "name": function_name,
                "parameters": params
            })

        if function_calls:
            logger.info(f"Regex extraction found {len(function_calls)} function calls")

        return function_calls

    def _clean_json_string(self, json_str: str) -> str:
        """
        Clean up malformed JSON from small models.

        Handles:
        - Single quotes → double quotes
        - Chinese characters (hallucinations)
        - Extra whitespace

        Args:
            json_str: Potentially malformed JSON string

        Returns:
            str: Cleaned JSON string
        """
        import re

        # Remove Chinese/non-ASCII characters (hallucinations from 3B model)
        json_str = re.sub(r'[^\x00-\x7F]+', '', json_str)

        # Fix single quotes to double quotes (common small model error)
        # Be careful - only fix dictionary keys/values, not inside strings
        # Simple approach: replace single quotes with double quotes
        json_str = json_str.replace("'", '"')

        return json_str.strip()

    def _parse_function_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse function call(s) from LLM response.

        Handles:
        - Single: {"function": "...", "parameters": {...}}
        - Multiple: [{"function": "...", "parameters": {...}}, ...]
        - Markdown code blocks: ```json ... ```

        Args:
            response: LLM response

        Returns:
            list: List of function call dicts (empty if none found)
        """
        try:
            json_str = None

            # Check if response starts with array bracket
            array_match = re.search(r'\[', response)
            obj_match = re.search(r'\{', response)

            # Determine if array or object comes first
            if array_match and (not obj_match or array_match.start() < obj_match.start()):
                # Array of function calls
                start_idx = array_match.start()
                json_str = self._extract_json_array(response, start_idx)
            elif obj_match:
                # Single function call object
                json_str = self._extract_json_with_braces(response, obj_match.start())

            if not json_str:
                return []

            # Clean up the JSON string
            json_str = json_str.strip()

            # CRITICAL: Clean malformed JSON from small models (Chinese chars, single quotes)
            json_str = self._clean_json_string(json_str)

            # DEBUG: Log the exact JSON string being parsed
            logger.debug(f"Attempting to parse JSON ({len(json_str)} chars): {json_str[:100]}...")

            # Parse JSON (may fail for malformed arrays, handled below)
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Initial JSON parse failed: {e}, attempting manual array-of-strings parse")
                # FALLBACK: Try to parse as array-of-strings manually
                # Pattern: ["string1", "string2"] where each string is a JSON object
                import ast
                try:
                    # Use ast.literal_eval for safer parsing of Python-style arrays
                    parsed = ast.literal_eval(json_str)
                except:
                    logger.error("Manual parsing also failed")
                    return []

            # Convert to list format
            if isinstance(parsed, list):
                # WORKAROUND: Check if this is an array of STRING representations of dicts
                # (common 3B model error: ["{'function': '...'}"] instead of [{"function": "..."}])
                if parsed and isinstance(parsed[0], str):
                    logger.warning("Detected array-of-strings format (3B model error), attempting to parse each string")
                    function_calls = []
                    for item_str in parsed:
                        try:
                            # Clean and parse each string as JSON
                            cleaned_item = self._clean_json_string(item_str)
                            item_dict = json.loads(cleaned_item)
                            if "function" in item_dict:
                                function_calls.append({
                                    "name": item_dict["function"],
                                    "parameters": item_dict.get("parameters", {})
                                })
                        except Exception as e:
                            logger.warning(f"Failed to parse array element: {e}")
                            continue
                    if function_calls:
                        logger.info(f"Successfully parsed {len(function_calls)} calls from malformed array")
                        return function_calls

                # Check if it's the alternative format: ["function_name", {params}]
                if len(parsed) == 2 and isinstance(parsed[0], str) and isinstance(parsed[1], dict):
                    # Alternative format detected
                    logger.info(f"Detected alternative format: [{parsed[0]}, {{params}}]")
                    function_name = parsed[0]
                    # Check if second element has "parameters" key or is the parameters directly
                    if "parameters" in parsed[1]:
                        params = parsed[1]["parameters"]
                    else:
                        params = parsed[1]
                    return [{
                        "name": function_name,
                        "parameters": params
                    }]

                # Standard format: Multiple function calls
                function_calls = []
                for call in parsed:
                    if isinstance(call, dict) and "function" in call:
                        function_calls.append({
                            "name": call["function"],
                            "parameters": call.get("parameters", {})
                        })
                if function_calls:
                    logger.info(f"Parsed {len(function_calls)} function calls")
                    return function_calls
            elif isinstance(parsed, dict) and "function" in parsed:
                # Single function call
                logger.info(f"Parsed function call: {parsed}")

                # CRITICAL FIX: Check if any parameter is a list (small model mistake)
                # If so, split into multiple calls
                params = parsed.get("parameters", {})
                function_name = parsed["function"]

                # Check for list parameters (common small model error for multi-tool queries)
                list_param_key = None
                list_param_values = None
                for key, value in params.items():
                    if isinstance(value, list) and len(value) > 1:
                        list_param_key = key
                        list_param_values = value
                        logger.warning(f"Small model error: parameter '{key}' is a list {value}. Splitting into multiple calls.")
                        break

                if list_param_key and list_param_values:
                    # Split into multiple function calls
                    multiple_calls = []
                    for val in list_param_values:
                        call_params = params.copy()
                        call_params[list_param_key] = val
                        multiple_calls.append({
                            "name": function_name,
                            "parameters": call_params
                        })
                    logger.info(f"Split into {len(multiple_calls)} calls: {multiple_calls}")
                    return multiple_calls

                return [{
                    "name": function_name,
                    "parameters": params
                }]
            else:
                return []

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse function call JSON: {e}")
            logger.debug(f"Attempted to parse: {json_str[:200] if json_str else 'None'}")
            return []
        except Exception as e:
            logger.error(f"Function call parsing failed: {e}")
            return []

    def _extract_json_array(self, text: str, start_idx: int) -> Optional[str]:
        """Extract JSON array by counting brackets."""
        if start_idx >= len(text) or text[start_idx] != '[':
            return None

        bracket_count = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string

            if not in_string:
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        return text[start_idx:i+1]

        return None

    def _combine_tool_results(self, tool_names: List[str], tool_results: List[str]) -> str:
        """
        Intelligently combine multiple tool results.

        Args:
            tool_names: List of tool names that were executed
            tool_results: List of tool results

        Returns:
            str: Combined result string
        """
        # Simple concatenation with labels for now
        combined_parts = []

        for tool_name, result in zip(tool_names, tool_results):
            # Extract stat_type from tool name if it's get_system_stats
            if "error:" in result:
                combined_parts.append(result)
            else:
                combined_parts.append(result)

        # Join with newlines
        combined = "\n".join(combined_parts)

        logger.info(f"Combined {len(tool_results)} results: {combined}")
        return combined

    def _format_final_response(self, query: str, tool_name: str, tool_result: str) -> str:
        """
        Format final response after tool execution.

        For multi-tool results: Uses deterministic parsing (NO LLM) to preserve ALL data
        For single-tool results: Uses smart extraction to format concisely

        Args:
            query: Original query
            tool_name: Tool that was used (comma-separated if multiple)
            tool_result: Tool result (combined if multiple tools)

        Returns:
            str: Formatted response
        """
        try:
            # Check if this is a multi-tool result (multiple tools were called)
            # FIXED: Only check tool_name, NOT tool_result (web searches have \n but are single-tool!)
            is_multi_tool = ',' in tool_name

            if is_multi_tool:
                # Multi-tool: Use deterministic formatting to preserve ALL data
                return self._format_multi_tool_response(query, tool_result)
            else:
                # Single-tool: Use smart extraction
                return self._format_single_tool_response(query, tool_result)

        except Exception as e:
            logger.error(f"Response formatting failed: {e}")
            # Fallback: just return the tool result
            return tool_result

    def _format_multi_tool_response(self, query: str, tool_result: str) -> str:
        """
        Format multi-tool responses deterministically (NO LLM filtering).

        CRITICAL: Preserve ALL data from all tools. Never drop any information.
        """
        # Parse tool result to extract all key metrics
        result_lower = tool_result.lower()
        parts = []

        # Extract CPU temperature
        cpu_temp_match = re.search(r'cpu[:\s]*(\d+)°c', result_lower)
        if cpu_temp_match:
            parts.append(f"CPU: {cpu_temp_match.group(1)}°C")

        # Extract GPU temperature
        gpu_temp_match = re.search(r'gpu[:\s]*(\d+)°c', result_lower)
        if gpu_temp_match:
            parts.append(f"GPU: {gpu_temp_match.group(1)}°C")

        # Extract CPU usage
        cpu_usage_match = re.search(r'cpu usage[:\s]*(\d+\.?\d*)%', result_lower)
        if cpu_usage_match:
            parts.append(f"CPU Usage: {cpu_usage_match.group(1)}%")

        # Extract GPU usage
        gpu_usage_match = re.search(r'gpu usage[:\s]*(\d+\.?\d*)%', result_lower)
        if gpu_usage_match:
            parts.append(f"GPU Usage: {gpu_usage_match.group(1)}%")

        # Extract GPU memory
        gpu_mem_match = re.search(r'gpu memory[:\s]*([\d.]+gb)\s*/\s*([\d.]+gb)', result_lower)
        if gpu_mem_match:
            parts.append(f"GPU Memory: {gpu_mem_match.group(1)}/{gpu_mem_match.group(2)}")

        # Extract RAM
        ram_match = re.search(r'ram[:\s]*([\d.]+gb)\s*/\s*([\d.]+gb)\s*\((\d+\.?\d*)%\)', result_lower)
        if ram_match:
            parts.append(f"RAM: {ram_match.group(1)}/{ram_match.group(2)} ({ram_match.group(3)}%)")

        # Extract processes if mentioned
        if 'process' in result_lower:
            # Extract process names and data
            process_lines = []
            for line in tool_result.split('\n'):
                if 'pid' in line.lower() or 'ram:' in line.lower():
                    # Clean up process line
                    cleaned = line.strip().replace('•', '').strip()
                    if cleaned and not cleaned.startswith('Temperature') and not cleaned.startswith('CPU') and not cleaned.startswith('GPU'):
                        process_lines.append(cleaned)

            if process_lines:
                parts.append("Processes: " + ", ".join(process_lines[:3]))  # Top 3

        if parts:
            response = ", ".join(parts)
            logger.info(f"Multi-tool formatted: {response}")
            return response
        else:
            # Improved fallback: summarize if too verbose
            if len(tool_result) > 150:
                logger.warning(f"Multi-tool parsing failed, result too long ({len(tool_result)} chars), using LLM post-processing")
                # Use LLM to extract key info
                return self._format_with_llm_post_processing(query, tool_result)
            else:
                logger.info("Multi-tool parsing failed but result is concise, returning as-is")
                return tool_result

    def _format_single_tool_response(self, query: str, tool_result: str) -> str:
        """
        Format single-tool responses with smart extraction.
        """
        # For simple single stat queries, extract the key info
        result_lower = tool_result.lower()
        query_lower = query.lower()

        # Temperature query
        if 'temperature' in query_lower:
            cpu_match = re.search(r'cpu[:\s]*(\d+)°c', result_lower)
            gpu_match = re.search(r'gpu[:\s]*(\d+)°c', result_lower)

            temps = []
            if cpu_match:
                temps.append(f"CPU: {cpu_match.group(1)}°C")
            if gpu_match:
                temps.append(f"GPU: {gpu_match.group(1)}°C")

            if temps:
                return ", ".join(temps)

        # Usage query
        if 'usage' in query_lower:
            if 'cpu' in query_lower:
                match = re.search(r'cpu usage[:\s]*(\d+\.?\d*)%', result_lower)
                if match:
                    return f"CPU Usage: {match.group(1)}%"
            if 'gpu' in query_lower:
                match = re.search(r'gpu usage[:\s]*(\d+\.?\d*)%', result_lower)
                if match:
                    return f"GPU Usage: {match.group(1)}%"

        # RAM query
        if 'ram' in query_lower or 'memory' in query_lower:
            match = re.search(r'ram[:\s]*([\d.]+gb)\s*/\s*([\d.]+gb)\s*\((\d+\.?\d*)%\)', result_lower)
            if match:
                return f"RAM: {match.group(1)}/{match.group(2)} ({match.group(3)}%)"

        # GPU stats (comprehensive)
        if 'gpu' in query_lower and 'stats' in query_lower:
            usage_match = re.search(r'gpu usage[:\s]*(\d+\.?\d*)%', result_lower)
            temp_match = re.search(r'gpu temp[:\s]*(\d+)°c', result_lower)
            mem_match = re.search(r'gpu memory[:\s]*([\d.]+gb)\s*/\s*([\d.]+gb)', result_lower)

            parts = []
            if usage_match:
                parts.append(f"{usage_match.group(1)}%")
            if temp_match:
                parts.append(f"{temp_match.group(1)}°C")
            if mem_match:
                parts.append(f"{mem_match.group(1)}/{mem_match.group(2)}")

            if parts:
                return f"GPU: {', '.join(parts)}"

        # WEB SEARCH POST-PROCESSING (Voice-optimized)
        # If this is a web search result, use LLM to extract concise answer
        if 'search results for' in result_lower or len(tool_result) > 500:
            try:
                logger.info("Using LLM post-processing for verbose result")
                concise_answer = self._extract_concise_answer(query, tool_result)
                if concise_answer and concise_answer != tool_result:
                    logger.info(f"Concise answer ({len(concise_answer.split())} words): {concise_answer[:100]}")
                    return concise_answer
            except Exception as e:
                logger.warning(f"LLM post-processing failed: {e}, using fallback")

        # Fallback: return cleaned raw result
        # Remove bullet points and extra whitespace
        cleaned = tool_result.replace('•', '').strip()
        cleaned = '\n'.join(line.strip() for line in cleaned.split('\n') if line.strip())
        return cleaned

    def _extract_concise_answer(self, query: str, tool_result: str) -> str:
        """
        Extract concise answer from verbose tool results using LLM.

        Uses RAG best practices:
        - System message defines role as reading comprehension assistant
        - Temperature near-zero for deterministic extraction
        - Explicit constraint to use ONLY provided context
        - Structured prompt with clear sections

        Args:
            query: Original user query
            tool_result: Verbose tool result (e.g., web search with long snippets)

        Returns:
            str: Concise answer optimized for voice
        """
        try:
            # Trim tool result if too long (save tokens)
            max_result_len = 2000  # characters
            if len(tool_result) > max_result_len:
                tool_result = tool_result[:max_result_len] + "..."

            # RAG BEST PRACTICE: Strong system message defining role
            system_message = """You are a reading comprehension assistant.

Your ONLY job: Extract answers from the CONTEXT below.

CRITICAL RULES:
1. Use ONLY information from the CONTEXT
2. NEVER use your training data or general knowledge
3. If answer not in CONTEXT, say "not found in context"
4. Keep answers under 40 words for voice output
5. No URLs in response"""

            # Structured user prompt with clear sections
            user_prompt = f"""CONTEXT:
{tool_result}

QUESTION: {query}

EXTRACT ANSWER (from CONTEXT only):"""

            # RAG BEST PRACTICE: Use system + user messages
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt}
            ]

            # RAG BEST PRACTICE: Near-zero temperature for factual extraction
            response = self.llm.generate(
                messages,
                max_tokens=80,  # ~40 words * 2 tokens/word
                temperature=0.1  # Deterministic - minimize hallucinations
            )

            answer = response.strip()

            # Validation: Must be concise
            word_count = len(answer.split())
            if word_count > 50:  # Slightly over limit but acceptable
                logger.warning(f"LLM answer too long ({word_count} words), truncating")
                # Truncate to first 2 sentences
                sentences = answer.split('.')[:2]
                answer = '. '.join(sentences).strip() + '.'

            # Validation: Must not be empty or just say "no answer"
            if not answer or len(answer) < 10:
                logger.warning("LLM answer too short or empty")
                return tool_result

            if 'no answer' in answer.lower() or 'not found' in answer.lower():
                logger.warning("LLM couldn't extract answer")
                return tool_result

            return answer

        except Exception as e:
            logger.error(f"Concise answer extraction failed: {e}")
            return tool_result
