import re
import json
import ollama
from typing import Dict, Any, List
from config.settings import Settings
from utils.logger import logger

class OllamaLLM:
    """Wrapper class for communicating with local Ollama models."""
    
    def __init__(self):
        self.model = Settings.OLLAMA_MODEL
        self.host = Settings.OLLAMA_HOST
        self.temperature = Settings.LLM_TEMPERATURE
        
        # Configure the ollama client host if custom
        if self.host != "http://localhost:11434":
            # For newer ollama python package, we can set host or let it use env var.
            # We'll log the configuration details.
            logger.debug(f"Ollama client initialized with host: {self.host}")
            
    def chat(self, messages: List[Dict[str, str]], retries: int = 2) -> Dict[str, Any]:
        """Queries Ollama and ensures the response matches the expected JSON structure.
        
        Expected output structure:
        {
            "thought": "Thinking explanation...",
            "tool_name": "tool_to_call" or null,
            "tool_args": { ... } or {}
        }
        """
        for attempt in range(retries + 1):
            try:
                logger.debug(f"Querying Ollama model '{self.model}' (Attempt {attempt + 1})...")
                response = ollama.chat(
                    model=self.model,
                    messages=messages,
                    format="json",
                    options={
                        "temperature": self.temperature
                    }
                )
                
                content = response["message"]["content"].strip()
                logger.debug(f"Raw LLM response:\n{content}")
                
                parsed_response = self._clean_and_parse_json(content)
                
                # Validation of required fields
                if "thought" not in parsed_response:
                    parsed_response["thought"] = content
                if "tool_name" not in parsed_response:
                    parsed_response["tool_name"] = None
                if "tool_args" not in parsed_response:
                    parsed_response["tool_args"] = {}
                    
                return parsed_response
                
            except Exception as e:
                logger.error(f"Error querying Ollama or parsing response (Attempt {attempt + 1}): {str(e)}")
                if attempt == retries:
                    # Final attempt failed, fallback to safe conversational response
                    return {
                        "thought": "Error occurred, falling back to safe response.",
                        "tool_name": None,
                        "tool_args": {},
                        "error": str(e)
                    }
                    
    def _clean_and_parse_json(self, text: str) -> Dict[str, Any]:
        """Cleans and extracts JSON structures from LLM outputs using regular expressions."""
        text = text.strip()
        
        # Scenario 1: JSON block within markdown code fence
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                logger.warning("Found JSON in markdown code blocks, but failed to parse it.")
                
        # Scenario 2: Find outermost curly braces (standard JSON extraction)
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_str = text[first_brace:last_brace + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as jde:
                logger.warning(f"Extracted JSON substring but failed to parse: {jde}")
                
        # Scenario 3: Standard string (likely purely conversational fallback)
        logger.debug("No valid JSON structure found in output. Treating as raw conversational response.")
        return {
            "thought": text,
            "tool_name": None,
            "tool_args": {}
        }
