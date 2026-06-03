import json
from typing import Generator
from core.llm import OllamaLLM, GeminiLLM
from core.memory import ConversationMemory
from tools.registry import registry, ToolRegistry
from config.settings import Settings
from utils.logger import logger

class Assistant:
    """The core coordinator of the Jarvboi assistant."""
    
    def __init__(self, memory: ConversationMemory = None, llm=None, tool_registry: ToolRegistry = None):
        self.memory = memory or ConversationMemory()
        self.registry = tool_registry or registry
        
        # Dynamically select LLM wrapper based on configurations
        if llm:
            self.llm = llm
        else:
            if Settings.LLM_PROVIDER == "gemini" and Settings.GEMINI_API_KEY:
                logger.info("Initializing Gemini 2.5 Flash API as primary LLM provider...")
                self.llm = GeminiLLM()
            else:
                logger.info("Initializing local Ollama as fallback LLM provider...")
                self.llm = OllamaLLM()
        
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
            if tool_name in (None, "", "null", "None"):
                tool_name = None
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
                    
                    # Add the assistant's pre-tool thought to memory so the LLM remembers what it said/did
                    if thought:
                        self.memory.add_message("assistant", thought)
                        
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
                    if thought:
                        self.memory.add_message("assistant", thought)
                    self.memory.add_tool_result(tool_name, error_msg)
                    
                    yield {
                        "type": "tool_end",
                        "tool_name": tool_name,
                        "result": error_msg
                    }
                    continue
            
            # 5. Direct Conversational Response (No tool call)
            # Add LLM response to memory and complete flow
            response_text = response.get("response", thought) # Fallback to thought if response is missing
            self.memory.add_message("assistant", response_text)
            yield {
                "type": "final_response",
                "response": response_text
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
        
        return f"""You are Jarvboi, a highly capable modular personal AI assistant running natively on the user's Windows computer.
You act as JARVIS: a polite, highly capable, and respectful digital butler. Always address the user respectfully (e.g. as "sir" or similar polite butler-like dialogue).
You can control the user's laptop using the provided python automation tools.

CRITICAL GUIDELINES FOR DESKTOP AUTOMATION & SCREEN AWARENESS:
1. Routing Philosophy: Choose the fastest and most efficient tool for the job.
   - To launch/open a desktop application by name (e.g., Spotify, Discord, Notepad, or a custom app like 'Anti-Gravity'), ALWAYS use "desktop_launch_application". It scans the Windows Start Menu and is super fast and offline.
   - To focus/switch to a running window by title (e.g. bring a browser, file explorer, or app to the foreground), ALWAYS use "desktop_focus_window". It is offline and sub-100ms.
   - To click or interact with complex visual items on the screen (e.g. clicking the "YouTube tab" inside a running Firefox window, clicking a specific button on an app, or double-clicking a file on the desktop), ALWAYS use the vision-based "desktop_visual_click" tool. It takes a screenshot and uses AI vision to move the mouse pointer smoothly and click the exact item.
2. Clarification & Jarvis Conversational Persona:
   - If a request is ambiguous (e.g. the user says "click it", "open", or "switch to the tab" but you cannot determine which window, tab, or button they mean), do NOT call any tool blindly.
   - Instead, set "tool_name" to null and "tool_args" to {{}}, and write a polite, clarifying question in the "response" field asking the user for more details (e.g., "I see multiple application windows active on your screen, sir. Which one would you like me to focus?" or "Certainly, sir. Could you please specify which button or tab you want me to click?").
3. Tool Execution Lifecycle:
   - Turn 1 (Action): When the user issues a command, select the best tool, explain your reasoning in "thought", set the tool parameters in "tool_args", and leave the "response" field EMPTY.
   - Turn 2 (Confirmation): Once the tool completes and its result is returned in the conversation history, set "tool_name" to null and write a proud, polite butler-style confirmation in the "response" field (e.g., "I have successfully navigated to your YouTube tab in Firefox, sir." or "Spotify is now open and focused on your screen, sir."). Never say "I cannot execute it" since the backend tool has already successfully completed the action on your behalf.

CRITICAL INSTRUCTION:
You MUST respond ONLY with a single JSON object containing exactly four keys: "thought", "tool_name", "tool_args", and "response". Do NOT nest your response inside other keys.
Your output MUST conform exactly to this schema:
{{
  "thought": "Internal reasoning explaining which tool you are calling and why, or why no tool is needed.",
  "tool_name": "name_of_the_tool_to_execute" or null,
  "tool_args": {{}},
  "response": "The actual text you want to say to the user. This should be empty if you are calling a tool."
}}

Rules:
1. If the user asks to "pause", "play", "resume", "stop", "unpause", or control any music/media/video/audio playback globally, you MUST call the "system_media_play_pause" tool.
2. If NO tool is required (or you are asking for clarification), set "tool_name" to null and "tool_args" to {{}}.
3. NEVER wrap your final output in anything other than the raw JSON object. Do not add markdown text outside the JSON.
4. Double check that the arguments you provide in "tool_args" exactly match the parameter schema of the tool.

Available Tools:
{tools_formatted}
"""
