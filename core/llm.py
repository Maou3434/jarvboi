import re
import json
import urllib.request
import ollama
from typing import Dict, Any, List
from config.settings import Settings
from utils.logger import logger

class GeminiLLM:
    """Wrapper class for communicating with Google Generative AI (Gemini 2.5 Flash API)."""
    
    def __init__(self):
        self.api_key = Settings.GEMINI_API_KEY
        self.model = Settings.GEMINI_MODEL
        self.temperature = Settings.LLM_TEMPERATURE
        
    def chat(self, messages: List[Dict[str, str]], retries: int = 2) -> Dict[str, Any]:
        """Queries the Gemini API over direct HTTP request, enforcing structured JSON outputs."""
        if not self.api_key:
            logger.error("GEMINI_API_KEY is not configured! Fallback to local Ollama...")
            # Fallback inline or raise error
            raise ValueError("GEMINI_API_KEY is missing.")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        # Convert standard chat history message formats to Gemini's expected contents format
        contents = []
        for msg in messages:
            role = "user"
            if msg["role"] == "assistant":
                role = "model"
                
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
            
        # Define payload for direct HTTP POST request with strict JSON schema enforcement
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "thought": {
                            "type": "STRING",
                            "description": "Direct conversational answer OR step-by-step reasoning explaining which tool you are calling and why."
                        },
                        "tool_name": {
                            "type": "STRING",
                            "description": "The name of the tool to execute, or null if no tool is needed."
                        },
                        "tool_args": {
                            "type": "OBJECT",
                            "description": "Arguments to pass to the tool. Must exactly match the tool's parameter schema. Empty object if tool_name is null."
                        }
                    },
                    "required": ["thought", "tool_name", "tool_args"]
                }
            }
        }
        
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload).encode("utf-8")
        
        for attempt in range(retries + 1):
            try:
                logger.debug(f"Querying Gemini API model '{self.model}' (Attempt {attempt + 1})...")
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                
                with urllib.request.urlopen(req, timeout=12.0) as response:
                    res_body = response.read().decode("utf-8")
                    res_json = json.loads(res_body)
                    
                    candidates = res_json.get("candidates", [])
                    if not candidates:
                        raise ValueError("No generation candidates returned from Gemini.")
                        
                    content_text = candidates[0]["content"]["parts"][0]["text"].strip()
                    logger.debug(f"Raw Gemini response text:\n{content_text}")
                    
                    parsed_response = json.loads(content_text)
                    return parsed_response
                    
            except Exception as e:
                logger.error(f"Error querying Gemini API (Attempt {attempt + 1}): {str(e)}")
                if attempt == retries:
                    # Final fallback to standard conversational response
                    return {
                        "thought": "I encountered an error querying the Gemini service: " + str(e),
                        "tool_name": None,
                        "tool_args": {},
                        "error": str(e)
                    }


class OllamaLLM:
    """Wrapper class for communicating with local Ollama models."""
    
    def __init__(self):
        self.model = Settings.OLLAMA_MODEL
        self.host = Settings.OLLAMA_HOST
        self.temperature = Settings.LLM_TEMPERATURE
        
        # Configure the ollama client host if custom
        if self.host != "http://localhost:11434":
            logger.debug(f"Ollama client initialized with host: {self.host}")
            
    def _find_conversational_value(self, data) -> str:
        """Recursively search for standard conversational values within dictionary/list structures."""
        if isinstance(data, dict):
            # Try specific conversational keys first
            for k in ["speech", "text", "Assistant", "assistant", "message", "thought", "response"]:
                if k in data:
                    val = data[k]
                    if isinstance(val, str) and val.strip():
                        stripped = val.strip()
                        # Verify this string is not itself nested JSON
                        if not (stripped.startswith("{") and stripped.endswith("}")):
                            return stripped
                    elif isinstance(val, (dict, list)):
                        res = self._find_conversational_value(val)
                        if res:
                            return res
            # Fallback: recurse into all dict values
            for v in data.values():
                res = self._find_conversational_value(v)
                if res:
                    return res
        elif isinstance(data, list):
            for item in data:
                res = self._find_conversational_value(item)
                if res:
                    return res
        return None

    def chat(self, messages: List[Dict[str, str]], retries: int = 2) -> Dict[str, Any]:
        """Queries Ollama and ensures the response matches the expected JSON structure."""
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
                
                # Validation and mapping of required fields using recursive conversational lookup
                if "thought" not in parsed_response or not parsed_response["thought"]:
                    conversational_val = self._find_conversational_value(parsed_response)
                    if conversational_val:
                        parsed_response["thought"] = conversational_val
                    else:
                        parsed_response["thought"] = content
                        
                if "tool_name" not in parsed_response:
                    parsed_response["tool_name"] = None
                if "tool_args" not in parsed_response:
                    parsed_response["tool_args"] = {}
                    
                return parsed_response
                
            except Exception as e:
                logger.error(f"Error querying Ollama or parsing response (Attempt {attempt + 1}): {str(e)}")
                if attempt == retries:
                    return {
                        "thought": "Error occurred, falling back to safe response.",
                        "tool_name": None,
                        "tool_args": {},
                        "error": str(e)
                    }
                    
    def _clean_and_parse_json(self, text: str) -> Dict[str, Any]:
        """Cleans and extracts JSON structures from LLM outputs, recursively unpacking nested fields."""
        text = text.strip()
        parsed_dict = None
        
        def find_conversational_value(data):
            """Recursively search for standard conversational values within dictionary/list structures."""
            if isinstance(data, dict):
                # Try specific conversational keys first
                for k in ["speech", "text", "Assistant", "assistant", "message", "thought", "response"]:
                    if k in data:
                        val = data[k]
                        if isinstance(val, str) and val.strip():
                            stripped = val.strip()
                            # Verify this string is not itself nested JSON
                            if not (stripped.startswith("{") and stripped.endswith("}")):
                                return stripped
                        elif isinstance(val, (dict, list)):
                            res = find_conversational_value(val)
                            if res:
                                return res
                # Fallback: recurse into all dict values
                for v in data.values():
                    res = find_conversational_value(v)
                    if res:
                        return res
            elif isinstance(data, list):
                for item in data:
                    res = find_conversational_value(item)
                    if res:
                        return res
            return None

        # Scenario 1: JSON block within markdown code fence
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if code_block_match:
            try:
                parsed_dict = json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                logger.warning("Found JSON in markdown code blocks, but failed to parse it.")
                
        # Scenario 2: Find outermost curly braces (standard JSON extraction)
        if not parsed_dict:
            first_brace = text.find('{')
            last_brace = text.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                json_str = text[first_brace:last_brace + 1]
                try:
                    parsed_dict = json.loads(json_str)
                except json.JSONDecodeError as jde:
                    logger.warning(f"Extracted JSON substring but failed to parse: {jde}")
                    
        if parsed_dict:
            # Robust mitigation: If the model nested a JSON string inside the "thought" field, unpack it
            if isinstance(parsed_dict.get("thought"), str):
                thought_str = parsed_dict["thought"].strip()
                if thought_str.startswith("{") and thought_str.endswith("}"):
                    unpacked = False
                    try:
                        # Clean raw single-quote escapes which are invalid in JSON standards
                        clean_thought_str = thought_str.replace("\\'", "'")
                        nested_json = json.loads(clean_thought_str)
                        conversational_val = find_conversational_value(nested_json)
                        if conversational_val:
                            parsed_dict["thought"] = conversational_val
                            unpacked = True
                    except Exception:
                        pass
                        
                    # Regex fallback if JSON parsing fails due to escaping/formatting quirks
                    if not unpacked:
                        match = re.search(r'"(?:speech|text|Assistant|assistant|message|thought|response)"\s*:\s*"(.*?)"', thought_str, re.DOTALL)
                        if match:
                            clean_text = match.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
                            parsed_dict["thought"] = clean_text
            return parsed_dict
            
        # Scenario 3: Standard string (likely purely conversational fallback)
        logger.debug("No valid JSON structure found in output. Treating as raw conversational response.")
        return {
            "thought": text,
            "tool_name": None,
            "tool_args": {}
        }
