"""
OpenAI Fallback System - For queries too complex for local LLM.

Privacy-first design:
1. Always try local LLM first
2. If confidence is low, ask user for voice confirmation
3. Only use OpenAI API with explicit permission
4. Track costs
5. Use cost-efficient model (gpt-4o-mini)

User workflow:
1. User: "explain quantum entanglement in detail"
2. System: "This is complex. Use OpenAI API? Cost: ~$0.01"
3. User: "yes" (voice)
4. System: Calls OpenAI, formats response, speaks answer
"""
import logging
import os
from typing import Optional, Dict, Any
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIFallback:
    """
    Handles fallback to OpenAI API for complex queries.

    Features:
    - Confidence scoring
    - Voice confirmation
    - Cost tracking
    - Privacy-first (only with permission)
    """

    # Cost per 1K tokens (approximate, as of 2025)
    COST_PER_1K_INPUT_TOKENS = 0.00015  # gpt-4o-mini input
    COST_PER_1K_OUTPUT_TOKENS = 0.0006  # gpt-4o-mini output

    def __init__(self, tts_engine: Optional[Any] = None, audio_capture: Optional[Any] = None):
        """
        Initialize OpenAI fallback.

        Args:
            tts_engine: TTS engine for voice confirmation prompts
            audio_capture: Audio capture for voice confirmation
        """
        self.tts = tts_engine
        self.audio = audio_capture

        # Initialize OpenAI client
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("OPENAI_API_KEY not set - fallback unavailable")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
            logger.info("OpenAI fallback initialized")

        # Cost tracking
        self.total_cost = 0.0
        self.query_count = 0

    def is_available(self) -> bool:
        """Check if OpenAI API is available."""
        return self.client is not None

    def should_use_fallback(self, query: str, local_response: str, confidence: float) -> bool:
        """
        Determine if query should use OpenAI fallback.

        Args:
            query: User query
            local_response: Response from local LLM
            confidence: Confidence score (0-1)

        Returns:
            bool: True if should use fallback
        """
        # Criteria for fallback:
        # 1. Low confidence (<0.6)
        # 2. Response is vague ("I can help with that", "Let me check")
        # 3. Query is very long (>50 words indicates complexity)
        # 4. Response contains errors/confusion

        if confidence < 0.6:
            logger.info(f"Low confidence ({confidence:.2f}) - suggesting fallback")
            return True

        # Check for vague responses
        vague_phrases = [
            "i can help",
            "let me check",
            "i will use",
            "i'll use",
            "i don't have",
            "i'm not sure",
            "could you clarify"
        ]

        response_lower = local_response.lower()
        if any(phrase in response_lower for phrase in vague_phrases):
            logger.info("Vague response detected - suggesting fallback")
            return True

        # Check for very long/complex queries
        word_count = len(query.split())
        if word_count > 50:
            logger.info(f"Complex query ({word_count} words) - suggesting fallback")
            return True

        return False

    def calculate_confidence(self, query: str, response: str) -> float:
        """
        Calculate confidence score for local LLM response.

        Heuristic-based scoring with multiple indicators.

        Args:
            query: User query
            response: Local LLM response

        Returns:
            float: Confidence score (0-1)
        """
        confidence = 1.0
        response_lower = response.lower()

        # STRONG reduction for vague/meta responses (LLM talking about using tools, not answering)
        vague_indicators = [
            "i will use", "i'll use", "let me use", "let's use",
            "i can help", "let me check", "i'll check",
            "please provide", "please clarify", "can you clarify"
        ]

        for indicator in vague_indicators:
            if indicator in response_lower:
                confidence -= 0.5  # STRONG penalty
                break

        # Reduce confidence for error indicators
        error_indicators = ["sorry", "couldn't", "can't", "don't know", "not sure"]

        for indicator in error_indicators:
            if indicator in response_lower:
                confidence -= 0.4
                break

        # Reduce confidence for very short responses to complex queries
        query_word_count = len(query.split())
        response_word_count = len(response.split())

        if query_word_count > 20 and response_word_count < 10:
            confidence -= 0.3

        # Reduce confidence if response doesn't answer the question
        # (Simple check: does response contain key words from query?)
        query_words = set(word.lower() for word in query.split() if len(word) > 3)
        response_words = set(word.lower() for word in response.split() if len(word) > 3)

        if query_words:  # Avoid division by zero
            overlap = len(query_words & response_words) / len(query_words)

            if overlap < 0.2:  # Less than 20% word overlap
                confidence -= 0.2

        return max(0.0, min(1.0, confidence))

    async def get_voice_confirmation(self, estimated_cost: float) -> bool:
        """
        Ask user for voice confirmation to use OpenAI API.

        Args:
            estimated_cost: Estimated cost in USD

        Returns:
            bool: True if user confirmed
        """
        if not self.tts or not self.audio:
            logger.warning("TTS/Audio not available for confirmation")
            return False

        try:
            # Ask user
            prompt = f"This query is complex. Use OpenAI API? Cost: approximately {estimated_cost:.3f} dollars. Say yes or no."

            logger.info(f"Asking for confirmation: {prompt}")

            # Speak prompt
            self.tts.speak(prompt)

            # Wait for voice response
            # TODO: Implement proper voice confirmation flow
            # For now, this is a placeholder that always returns False
            # Need to integrate with audio_capture and transcription

            logger.warning("Voice confirmation not yet implemented - returning False")
            return False

        except Exception as e:
            logger.error(f"Voice confirmation failed: {e}")
            return False

    def query_openai(
        self,
        query: str,
        context: Optional[str] = None,
        max_tokens: int = 500
    ) -> Dict[str, Any]:
        """
        Query OpenAI API with cost tracking.

        Args:
            query: User query
            context: Optional context from local LLM
            max_tokens: Maximum tokens for response

        Returns:
            dict: Response with 'text', 'cost', 'tokens'
        """
        if not self.client:
            return {
                'error': 'OpenAI API not available',
                'text': None,
                'cost': 0.0,
                'tokens': {'input': 0, 'output': 0}
            }

        try:
            # Build messages
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful AI assistant. Provide clear, accurate, concise responses suitable for text-to-speech."
                },
                {
                    "role": "user",
                    "content": query
                }
            ]

            # Add context if provided
            if context:
                messages.insert(1, {
                    "role": "assistant",
                    "content": f"Local analysis: {context}"
                })

            logger.info("Calling OpenAI API (gpt-4o-mini)")

            # Call API
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7
            )

            # Extract response
            text = response.choices[0].message.content

            # Calculate cost
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            cost = (
                (input_tokens / 1000) * self.COST_PER_1K_INPUT_TOKENS +
                (output_tokens / 1000) * self.COST_PER_1K_OUTPUT_TOKENS
            )

            # Track cost
            self.total_cost += cost
            self.query_count += 1

            logger.info(f"OpenAI response received - Cost: ${cost:.4f}, Total: ${self.total_cost:.4f}")

            return {
                'text': text,
                'cost': cost,
                'tokens': {
                    'input': input_tokens,
                    'output': output_tokens
                },
                'error': None
            }

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}", exc_info=True)
            return {
                'error': str(e),
                'text': None,
                'cost': 0.0,
                'tokens': {'input': 0, 'output': 0}
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cost statistics.

        Returns:
            dict: Usage statistics
        """
        return {
            'total_cost': self.total_cost,
            'query_count': self.query_count,
            'avg_cost_per_query': self.total_cost / max(self.query_count, 1)
        }
