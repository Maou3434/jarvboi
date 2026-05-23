import json
from typing import Generator
from core.llm import OllamaLLM
from core.memory import ConversationMemory
from tools.registry import registry, ToolRegistry
from utils.logger import logger

class Assistant:
    """The core coordinator of the Jarvboi assistant."""
    
    def __init__(self, memory: ConversationMemory = None, llm: OllamaLLM = None, tool_registry: ToolRegistry = None):
        self.memory = memory or ConversationMemory()
        self.llm = llm or OllamaLLM()
        self.registry = tool_registry or registry
        
    def execute(self, user_message: str, max_turns: int = 3) -> Generator[dict, None, None]:
        """Processes a user message, executing tools dynamically and yielding step details.
        
        Yields:
            Dict containing step information (type, thought, tool_name, result, response).
        """
        # 1. Add user message to conversation memory
        self.memory.add_message("user", user_message)
        
        for turn in range(max_turns):
            logger.debug(f"Starting execution turn {turn + 1}/{max_turns}")
            
            # 2. Formulate dynamic system prompt and prepare full message history
            system_prompt = self._get_system_prompt()
            messages = [{"role": "system", "content": system_prompt}] + self.memory.get_history()
            
            # 3. Query LLM
            response = self.llm.chat(messages)
            thought = response.get("thought", "")
            tool_name = response.get("tool_name")
            tool_args = response.get("tool_args", {})
            
            yield {
                "type": "thought",
                "thought": thought,
                "tool_name": tool_name,
                "tool_args": tool_args
            }
            
            # 4. Handle Tool Calls
            if tool_name:
                tool = self.registry.get_tool(tool_name)
                if tool:
                    logger.info(f"Executing tool '{tool_name}' with args: {tool_args}")
                    yield {
                        "type": "tool_start",
                        "tool_name": tool_name,
                        "tool_args": tool_args
                    }
                    
                    # Execute tool
                    result = tool.execute(**tool_args)
                    logger.info(f"Tool '{tool_name}' execution result: {result}")
                    
                    # Add execution result to memory
                    self.memory.add_tool_result(tool_name, result)
                    
                    yield {
                        "type": "tool_end",
                        "tool_name": tool_name,
                        "result": result
                    }
                    
                    # Continue loop to let model formulate final response based on tool result
                    continue
                else:
                    error_msg = f"Tool '{tool_name}' is not registered."
                    logger.warning(error_msg)
                    self.memory.add_tool_result(tool_name, error_msg)
                    
                    yield {
                        "type": "tool_end",
                        "tool_name": tool_name,
                        "result": error_msg
                    }
                    continue
            
            # 5. Direct Conversational Response (No tool call)
            # Add LLM response to memory and complete flow
            self.memory.add_message("assistant", json.dumps(response))
            yield {
                "type": "final_response",
                "response": thought
            }
            break
        else:
            # Reached max turns without a final response
            logger.warning("Reached maximum turn execution depth without final response.")
            yield {
                "type": "final_response",
                "response": "I executed my tools, but I reached my turn limit before finishing the response."
            }
            
    def _get_system_prompt(self) -> str:
        """Generates a dynamic system prompt embedded with the current tool schemas."""
        tools_list = self.registry.list_tools()
        tools_formatted = json.dumps(tools_list, indent=2)
        
        return f"""You are Jarvboi, a highly capable modular personal AI assistant.
You operate using structured tool execution.

CRITICAL INSTRUCTION:
You MUST respond ONLY with a single JSON object containing exactly three keys: "thought", "tool_name", and "tool_args". Do NOT nest your response inside other keys (like "conversation" or "role").
Your output MUST conform exactly to this schema:
{{
  "thought": "Direct response to user OR detailed rationale explaining which tool you are calling and why.",
  "tool_name": "name_of_the_tool_to_execute" or null,
  "tool_args": {{}}
}}

Rules:
1. If the user asks you to open a website, search YouTube, or perform any action matching an available tool, select the appropriate tool and set "tool_name" and "tool_args" accordingly.
2. If the user asks to "pause", "play", "resume", "stop", "unpause", or control any music, media, video, or audio playback, you MUST call the "system_media_play_pause" tool. Set "tool_name" to "system_media_play_pause" and "tool_args" to {{}}.
3. If NO tool is required, set "tool_name" to null and "tool_args" to {{}}. Use the "thought" field to write your conversational response to the user.
4. When a tool execution result is provided in the conversation history, do NOT call the tool again. Set "tool_name" to null and "tool_args" to {{}} and write a friendly response in the "thought" field confirming that the action was successfully executed (e.g. "I've successfully opened the website!" or "I've started playing that video on YouTube for you!").
5. NEVER wrap your final output in anything other than the raw JSON object. Do not add conversational text outside the JSON.
6. Double check that the arguments you provide in "tool_args" exactly match the parameter schema of the tool.

Available Tools:
{tools_formatted}
"""
