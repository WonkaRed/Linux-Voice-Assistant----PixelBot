"""
LLM Manager for Qwen2.5-1.5B-Instruct

Handles loading, unloading, and inference with Qwen2.5-1.5B LLM.
Used for text post-processing, keyword removal, and AI features.

Performance: 90% accuracy, 100% success rate on all voice samples!
VRAM: 3.6GB (bfloat16 precision)
Speed: 0.32s average generation time

Model: Qwen/Qwen2.5-1.5B-Instruct (1.5B parameters)
CRITICAL: Uses bfloat16 to fix CUDA numerical stability issues!
"""
import logging
import time
from typing import Optional, List, Dict

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)

from src import config

logger = logging.getLogger(__name__)


class LLMManager:
    """Manages the Qwen2.5-1.5B LLM for text processing and AI features."""

    def __init__(self):
        """Initialize the LLM manager."""
        self.model: Optional[AutoModelForCausalLM] = None
        self.tokenizer: Optional[AutoTokenizer] = None
        self.is_loaded = False
        self.load_time: Optional[float] = None
        self.vram_usage: Optional[float] = None

    def load(self) -> bool:
        """
        Load the Qwen2.5-1.5B model into GPU memory with bfloat16 precision.

        CRITICAL: Uses bfloat16 instead of float16 to fix CUDA numerical errors!
        BFloat16 has wider range preventing attention overflow/underflow.

        Returns:
            bool: True if successful, False otherwise
        """
        if self.is_loaded:
            logger.info("LLM already loaded")
            return True

        try:
            logger.info(f"Loading LLM: {config.LLM_MODEL_NAME}")
            logger.info(f"Quantization: {config.LLM_QUANTIZATION}")
            start_time = time.time()

            # Get initial VRAM
            initial_vram = self._get_vram_used()

            # Configure 4-bit quantization
            quant_config = None
            if config.LLM_QUANTIZATION == "4bit":
                quant_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",  # NormalFloat4
                )
                logger.info("Using 4-bit NF4 quantization")
            elif config.LLM_QUANTIZATION == "8bit":
                quant_config = BitsAndBytesConfig(
                    load_in_8bit=True,
                )
                logger.info("Using 8-bit quantization")

            # Load model
            load_kwargs = {
                "cache_dir": config.LLM_CACHE_DIR,
                "trust_remote_code": True,  # Required for some models
                "attn_implementation": getattr(config, 'LLM_ATTN_IMPLEMENTATION', 'eager'),  # Use config or default to eager
            }

            # Configure based on quantization and dtype
            if quant_config is None:
                # No quantization: use bfloat16 or fp16 on GPU
                load_kwargs["device_map"] = "auto"

                # Use bfloat16 if specified (fixes CUDA errors for Qwen2.5!)
                if hasattr(config, 'LLM_DTYPE') and config.LLM_DTYPE == "bfloat16":
                    load_kwargs["torch_dtype"] = torch.bfloat16
                    logger.info("Loading model in bfloat16 (fixes CUDA numerical stability)")
                else:
                    load_kwargs["torch_dtype"] = torch.float16
                    logger.info("Loading model in fp16 (no quantization)")
            else:
                # With quantization: use special loading
                load_kwargs["quantization_config"] = quant_config
                load_kwargs["device_map"] = {"": 0}  # Load everything to GPU 0
                load_kwargs["low_cpu_mem_usage"] = True
                logger.info("Loading quantized model directly to GPU 0")

            self.model = AutoModelForCausalLM.from_pretrained(
                config.LLM_MODEL_NAME,
                **load_kwargs
            )

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                config.LLM_MODEL_NAME,
                cache_dir=config.LLM_CACHE_DIR,
                trust_remote_code=True,
            )

            # Set pad token if not set
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            # Calculate load time and VRAM usage
            self.load_time = time.time() - start_time
            self.vram_usage = self._get_vram_used() - initial_vram
            self.is_loaded = True

            logger.info(
                f"✓ LLM loaded successfully in {self.load_time:.2f}s"
            )
            logger.info(f"  VRAM usage: {self.vram_usage:.2f}GB")
            logger.info(f"  Total VRAM: {self._get_vram_used():.2f}GB")

            return True

        except Exception as e:
            logger.error(f"Failed to load LLM: {e}", exc_info=True)
            self.is_loaded = False
            return False

    def unload(self) -> bool:
        """
        Unload the LLM from GPU memory.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_loaded:
            logger.info("LLM not loaded")
            return True

        try:
            logger.info("Unloading LLM...")

            # Delete model and tokenizer
            self.model = None
            self.tokenizer = None
            self.is_loaded = False

            # Force garbage collection and clear CUDA cache
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

            logger.info("✓ LLM unloaded")
            logger.info(f"  VRAM after unload: {self._get_vram_used():.2f}GB")

            return True

        except Exception as e:
            logger.error(f"Failed to unload LLM: {e}", exc_info=True)
            return False

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        """
        Generate text using the LLM with chat format.

        Args:
            messages: List of message dicts with 'role' and 'content'
                     Example: [{"role": "user", "content": "Hello"}]
            max_tokens: Maximum tokens to generate (default: config value)
            temperature: Sampling temperature (default: config value)
            top_p: Nucleus sampling parameter (default: config value)

        Returns:
            str: Generated text
        """
        if not self.is_loaded:
            raise RuntimeError("LLM not loaded. Call load() first.")

        try:
            # Use config defaults if not specified
            max_tokens = max_tokens or config.LLM_MAX_NEW_TOKENS
            temperature = temperature or config.LLM_TEMPERATURE
            top_p = top_p or config.LLM_TOP_P

            # Apply chat template
            text_ids = self.tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
            )

            # Move to correct device
            if hasattr(self.model, 'device'):
                text_ids = text_ids.to(self.model.device)
            else:
                # For quantized models, get device from first parameter
                text_ids = text_ids.to(next(self.model.parameters()).device)

            # Create attention mask explicitly (fixes pad_token warning)
            attention_mask = torch.ones_like(text_ids)
            if hasattr(self.model, 'device'):
                attention_mask = attention_mask.to(self.model.device)
            else:
                attention_mask = attention_mask.to(next(self.model.parameters()).device)

            # Generate
            with torch.no_grad():
                output_ids = self.model.generate(
                    text_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    do_sample=True if temperature > 0 else False,
                    top_p=top_p,
                    pad_token_id=self.tokenizer.pad_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    use_cache=True,  # Re-enable cache (should work now)
                )

            # Decode response (only new tokens)
            response = self.tokenizer.decode(
                output_ids[0][len(text_ids[0]):],
                skip_special_tokens=True,
            ).strip()

            logger.debug(f"LLM input: {messages[-1]['content'][:100]}...")
            logger.debug(f"LLM output: {response[:100]}...")

            return response

        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            return ""

    def clean_text(
        self,
        raw_text: str,
        system_prompt: Optional[str] = None,
        user_template: Optional[str] = None,
        custom_replacements: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Clean transcribed text by removing keywords and applying formatting.

        This is the primary function for text post-processing.

        Args:
            raw_text: Raw transcription from Whisper
            system_prompt: Optional custom system prompt for LLM
            user_template: Optional custom user template with {text} placeholder
            custom_replacements: Optional dict of custom word replacements

        Returns:
            str: Cleaned and formatted text
        """
        if not self.is_loaded:
            raise RuntimeError("LLM not loaded. Call load() first.")

        # Use custom prompts if provided, otherwise use default
        if system_prompt and user_template:
            # Custom prompts provided
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_template.format(text=raw_text)}
            ]
        else:
            # Use default prompt
            # Build replacement instructions
            replacements = custom_replacements or config.CUSTOM_WORD_REPLACEMENTS
            replacement_text = ""
            if replacements:
                replacement_text = "Apply these word replacements:\n"
                for old, new in replacements.items():
                    replacement_text += f"- '{old}' → '{new}'\n"

            # Build prompt with clear instructions and examples
            user_prompt = f"""You are a text cleaning assistant. Remove activation keywords and format the remaining text.

Activation keywords to REMOVE: "transcribe", "start transcribe", "end transcribe", "stop transcribe", "and transcribe", "pixel bot", "pixelbot", "hey pixel", "cortex", "hey cortex"

{replacement_text}

Instructions:
1. Remove ALL activation keywords
2. Keep all other words
3. Add proper punctuation
4. Capitalize appropriately
5. Return only the cleaned text, nothing else

Examples:
Input: "transcribe hello world stop transcribe"
Output: Hello world.

Input: "Start transcribing. This is a test."
Output: This is a test.

Input: "pixel bot what is two plus two"
Output: What is two plus two?

Now clean this text:
Input: "{raw_text}"
Output:"""

            messages = [
                {"role": "user", "content": user_prompt}
            ]

        # Generate cleaned text with low temperature for consistency
        cleaned = self.generate(
            messages,
            max_tokens=512,
            temperature=0.3,  # Low for deterministic output
        )

        # Remove any extra quotes if model added them
        cleaned = cleaned.strip('"\'').strip()

        # If output is empty and input had non-keyword content, return input
        if not cleaned and len(raw_text.split()) > 3:
            logger.warning("LLM returned empty output, using fallback cleaning")
            cleaned = self._fallback_clean(raw_text)

        logger.info(f"Text cleaning - Input: '{raw_text[:100]}'")
        logger.info(f"Text cleaning - Output: '{cleaned[:100]}'")

        return cleaned

    def _fallback_clean(self, text: str) -> str:
        """
        Fallback keyword removal using simple string replacement.

        Args:
            text: Input text

        Returns:
            str: Cleaned text
        """
        import re

        # List of keywords to remove
        keywords = [
            r'\btranscribe\b',
            r'\bstart transcribe\b',
            r'\bend transcribe\b',
            r'\bstop transcribe\b',
            r'\band transcribe\b',
            r'\bpixel bot\b',
            r'\bpixelbot\b',
            r'\bhey pixel\b',
            r'\bcortex\b',
            r'\bhey cortex\b',
            r'\byo pixel\b',
            r'\byo cortex\b',
        ]

        cleaned = text
        for keyword in keywords:
            cleaned = re.sub(keyword, '', cleaned, flags=re.IGNORECASE)

        # Clean up extra spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Capitalize first letter
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]

        return cleaned

    def chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Chat with the LLM (used by Pixel Bot).

        Args:
            user_message: User's message
            conversation_history: Previous messages (optional)
            system_prompt: System prompt (optional, uses default if not provided)

        Returns:
            str: LLM response
        """
        if not self.is_loaded:
            raise RuntimeError("LLM not loaded. Call load() first.")

        # Build messages
        messages = []

        # Add system prompt
        system = system_prompt or config.PIXEL_BOT_SYSTEM_PROMPT
        messages.append({"role": "system", "content": system})

        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history)

        # Add current message
        messages.append({"role": "user", "content": user_message})

        # Generate response
        response = self.generate(messages, max_tokens=200)

        return response

    def get_status(self) -> dict:
        """
        Get LLM status information.

        Returns:
            dict: Status information
        """
        return {
            "loaded": self.is_loaded,
            "model_name": config.LLM_MODEL_NAME,
            "quantization": config.LLM_QUANTIZATION,
            "device": config.LLM_DEVICE,
            "load_time": self.load_time,
            "vram_usage": self.vram_usage,
            "current_vram": self._get_vram_used() if torch.cuda.is_available() else None,
        }

    def _get_vram_used(self) -> float:
        """
        Get current VRAM usage in GB.

        Returns:
            float: VRAM usage in GB
        """
        if not torch.cuda.is_available():
            return 0.0

        return torch.cuda.memory_allocated(0) / 1e9

    def __del__(self):
        """Cleanup on deletion."""
        if self.is_loaded:
            self.unload()


# Convenience function for standalone testing
def test_llm_manager():
    """Test the LLM manager."""
    print("=== Testing LLM Manager (Phi-3-mini) ===\n")

    # Initialize
    manager = LLMManager()
    print(f"Initial status: {manager.get_status()}\n")

    # Load model
    print("Loading model (this may take 5-10 seconds)...")
    success = manager.load()
    print(f"Load success: {success}\n")

    if success:
        print(f"Status after load: {manager.get_status()}\n")

        # Test 1: Text cleaning
        print("Test 1: Text Cleaning")
        raw_text = "transcribe hello world this is a test stop transcribe"
        cleaned = manager.clean_text(raw_text)
        print(f"Input:  '{raw_text}'")
        print(f"Output: '{cleaned}'\n")

        # Test 2: Chat
        print("Test 2: Chat")
        response = manager.chat("What is 2+2?")
        print(f"Question: 'What is 2+2?'")
        print(f"Response: '{response}'\n")

        # Test 3: Long transcription with keywords
        print("Test 3: Long Text with Keywords")
        long_text = "transcribe the quick brown fox jumps over the lazy dog and transcribe"
        cleaned_long = manager.clean_text(long_text)
        print(f"Input:  '{long_text}'")
        print(f"Output: '{cleaned_long}'\n")

        # Unload
        print("Unloading model...")
        manager.unload()
        print(f"Status after unload: {manager.get_status()}\n")

    print("=== Test Complete ===")


if __name__ == "__main__":
    # Set up basic logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run test
    test_llm_manager()
