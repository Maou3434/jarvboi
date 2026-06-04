import json
from typing import Generator, List, Dict, Any, Optional
from core.state import AssistantState
from config.settings import Settings
from utils.logger import logger

def check_ollama_running() -> bool:
    """Checks if the local Ollama server is running and responsive."""
    try:
        import urllib.request
        with urllib.request.urlopen(Settings.OLLAMA_HOST, timeout=1.5) as conn:
            if conn.status in (200, 404):
                return True
    except Exception as e:
        import urllib.error
        if isinstance(e, urllib.error.HTTPError):
            return True
    return False


class Assistant:
    """The core coordinator of the Jarvboi assistant, refactored to support
    dependency injection, explicit state machine transitions, and event-driven orchestration.
    """
    
    def __init__(
        self,
        event_bus: Optional[Any] = None,
        llm_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        speech_service: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        skill_service: Optional[Any] = None
    ):
        # Lazy imports to prevent circular dependencies at startup
        from services.event_bus import EventBus
        from services.llm_service import LLMService
        from services.memory_service import MemoryService
        from services.speech_service import SpeechService
        from services.skill_service import SkillService
        from tools.registry import registry
        
        self.event_bus = event_bus or EventBus()
        self.llm_service = llm_service or LLMService()
        self.memory_service = memory_service or MemoryService(event_bus=self.event_bus)
        self.speech_service = speech_service or SpeechService(event_bus=self.event_bus)
        self.registry = tool_registry or registry
        self.skill_service = skill_service or SkillService(event_bus=self.event_bus)
        
        self.state = AssistantState.IDLE
        self.preferred_provider = Settings.LLM_PROVIDER
        self.awaiting_ollama_start = False
        self.awaiting_gemini_switch = False
        self.awaiting_skill_save = False
        self.pending_skill_data = {}
        self.has_gemini = bool(Settings.GEMINI_API_KEY)
        self.interrupted = False
        
        # Subscribe to Event Bus interruption triggers
        self.event_bus.subscribe("interrupt", self._on_interrupt)
        
    def _on_interrupt(self, data=None):
        logger.info("[Assistant] Interrupt event caught on bus. Setting interruption state.")
        self.interrupted = True
        self.set_state(AssistantState.INTERRUPTED)
        
    @property
    def memory(self):
        """Backward-compatibility property delegating to memory_service."""
        return self.memory_service
        
    def set_state(self, new_state: AssistantState):
        """Sets assistant state and publishes state_changed event on the Event Bus."""
        logger.info(f"[Assistant] State transitioning: {self.state.name} -> {new_state.name}")
        self.state = new_state
        self.event_bus.publish("state_changed", new_state)

    def execute(self, user_message: str, max_turns: int = 3) -> Generator[dict, None, None]:
        """Processes a user message, executing tools dynamically and yielding step details.
        
        Yields:
            Dict containing step information.
        """
        # Reset interruption state on new query execution
        self.interrupted = False
        
        clean_msg = user_message.lower().strip().replace(".", "").replace(",", "")
        affirmative_words = {"yes", "yeah", "yup", "ok", "okay", "sure", "please", "do it", "confirm", "go ahead", "y", "correct", "affirmative"}
        is_affirmative = any(w in affirmative_words for w in clean_msg.split()) or clean_msg in affirmative_words

        # Handle active wait state for switching to Gemini
        if self.awaiting_gemini_switch:
            self.awaiting_gemini_switch = False
            if is_affirmative:
                self.llm_service.switch_to_gemini()
                self.preferred_provider = "gemini"
                yield {
                    "type": "thought",
                    "thought": "User confirmed switching to Gemini API.",
                    "tool_name": None,
                    "tool_args": {}
                }
                yield {
                    "type": "final_response",
                    "response": "Certainly, sir. I have switched our LLM provider to Gemini. How can I assist you?"
                }
            else:
                yield {
                    "type": "thought",
                    "thought": "User declined switching to Gemini. Remaining in Ollama mode.",
                    "tool_name": None,
                    "tool_args": {}
                }
                yield {
                    "type": "final_response",
                    "response": "Understood, sir. I will remain in Ollama mode and wait for the service to start."
                }
            return

        # Handle active wait state for launching Ollama in WSL
        if self.awaiting_ollama_start:
            self.awaiting_ollama_start = False
            
            if is_affirmative:
                yield {
                    "type": "thought",
                    "thought": "User confirmed starting Ollama in WSL. Triggering command...",
                    "tool_name": None,
                    "tool_args": {}
                }
                yield {
                    "type": "final_response",
                    "response": "Certainly, sir. Starting the Ollama service in WSL now. Please wait a moment while it initializes..."
                }
                
                # Start Ollama in WSL
                import subprocess
                import time
                try:
                    subprocess.Popen(["wsl", "ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logger.info("[Ollama Manager] Executed background WSL startup command: wsl ollama serve")
                except Exception as e:
                    logger.error(f"[Ollama Manager] Failed to execute WSL command: {e}")
                    
                # Sleep to let the server spin up
                time.sleep(4.0)
                
                # Re-verify connection
                if check_ollama_running():
                    logger.info("[Ollama Manager] Ollama is now running.")
                    self.llm_service.switch_to_ollama()
                    yield {
                        "type": "final_response",
                        "response": "The Ollama service is now online in WSL and ready for use, sir. How can I assist you?"
                    }
                else:
                    logger.warning("[Ollama Manager] Ollama failed to respond after WSL start command.")
                    if self.has_gemini:
                        self.awaiting_gemini_switch = True
                        yield {
                            "type": "final_response",
                            "response": "I tried to start Ollama in WSL, sir, but the service is still not responding. Would you like me to switch to Gemini instead?"
                        }
                    else:
                        yield {
                            "type": "final_response",
                            "response": "I tried to start Ollama in WSL, sir, but the service is still not responding. I will remain in Ollama mode and wait for it."
                        }
            else:
                # User declined starting Ollama
                if self.has_gemini:
                    self.awaiting_gemini_switch = True
                    yield {
                        "type": "thought",
                        "thought": "User declined starting Ollama. Asking if they want to switch to Gemini.",
                        "tool_name": None,
                        "tool_args": {}
                    }
                    yield {
                        "type": "final_response",
                        "response": "Understood, sir. Would you like me to switch to Gemini instead?"
                    }
                else:
                    yield {
                        "type": "final_response",
                        "response": "Understood, sir. I will wait until the Ollama service becomes available."
                    }
            return

        # Handle active wait state for creating/saving custom skills
        if self.awaiting_skill_save:
            self.awaiting_skill_save = False
            skill_info = self.pending_skill_data
            self.pending_skill_data = {}
            
            if is_affirmative:
                self.set_state(AssistantState.THINKING)
                yield {
                    "type": "thought",
                    "thought": f"User confirmed skill creation. Writing skill files for '{skill_info.get('name')}' to disk...",
                    "tool_name": None,
                    "tool_args": {}
                }
                
                success = self.skill_service.create_skill(
                    name=skill_info.get("name"),
                    description=skill_info.get("description"),
                    parameters=skill_info.get("parameters"),
                    python_code=skill_info.get("python_code"),
                    markdown_content=skill_info.get("markdown_content")
                )
                
                if success:
                    response_msg = f"Certainly, sir. I have saved and loaded the skill '{skill_info.get('name')}'. It is now part of my permanent capabilities."
                else:
                    response_msg = f"I apologize, sir. I encountered an error while writing the python tool files for the skill '{skill_info.get('name')}'."
                    
                self.event_bus.publish("assistant_response", {"response": response_msg})
                yield {
                    "type": "final_response",
                    "response": response_msg
                }
            else:
                yield {
                    "type": "thought",
                    "thought": "User declined saving the proposed skill.",
                    "tool_name": None,
                    "tool_args": {}
                }
                yield {
                    "type": "final_response",
                    "response": "Understood, sir. I will not save this workflow as a skill."
                }
            self.set_state(AssistantState.IDLE)
            return
                
        # Intercept if local Ollama is preferred but currently offline
        if self.preferred_provider == "ollama" and not check_ollama_running():
            self.awaiting_ollama_start = True
            yield {
                "type": "thought",
                "thought": "Ollama service is not running. Asking user for permission to start it in WSL.",
                "tool_name": None,
                "tool_args": {}
            }
            yield {
                "type": "final_response",
                "response": "I noticed the local Ollama service is not running, sir. Would you like me to start it in WSL?"
            }
            return

        # Start thinking
        self.set_state(AssistantState.THINKING)
        
        # Track tools executed in this session
        executed_tools = []
        
        # Retrieve relevant past vector memories
        relevant_memories = []
        try:
            relevant_memories = self.memory_service.retrieve_long_term_context(user_message, top_k=3)
            if relevant_memories:
                logger.info(f"[Assistant] Injected {len(relevant_memories)} vector context strings.")
        except Exception as e:
            logger.error(f"[Assistant] Error retrieving long-term context: {e}")

        # Add user message to conversation memory
        self.memory_service.add_short_term_message("user", user_message)
        
        for turn in range(max_turns):
            if self.interrupted:
                logger.info("[Assistant] Interruption detected. Aborting execution loop.")
                yield {
                    "type": "final_response",
                    "response": "[Interrupted]"
                }
                self.set_state(AssistantState.IDLE)
                return

            logger.debug(f"Starting execution turn {turn + 1}/{max_turns}")
            
            # Formulate dynamic system prompt and prepare full message history
            system_prompt = self._get_system_prompt(relevant_memories, user_message)
            messages = [{"role": "system", "content": system_prompt}] + self.memory_service.get_short_term_history()
            
            # Query LLM Service
            response = self.llm_service.chat(messages)
            thought = response.get("thought", "")
            tool_name = response.get("tool_name")
            if tool_name in (None, "", "null", "None"):
                tool_name = None
            tool_args = response.get("tool_args", {})
            
            # Publish thought on the event bus
            self.event_bus.publish("assistant_thought", {"thought": thought})
            
            yield {
                "type": "thought",
                "thought": thought,
                "tool_name": tool_name,
                "tool_args": tool_args
            }
            
            # Handle Tool Calls
            if tool_name:
                self.set_state(AssistantState.TOOL_RUNNING)
                tool = self.registry.get_tool(tool_name)
                if tool:
                    logger.info(f"Executing tool '{tool_name}' with args: {tool_args}")
                    self.event_bus.publish("tool_start", {"tool_name": tool_name, "tool_args": tool_args})
                    yield {
                        "type": "tool_start",
                        "tool_name": tool_name,
                        "tool_args": tool_args
                    }
                    
                    if thought:
                        self.memory_service.add_short_term_message("assistant", thought)
                        
                    # Execute tool
                    result = tool.execute(**tool_args)
                    logger.info(f"Tool '{tool_name}' result: {result}")
                    
                    # Record execution trace
                    executed_tools.append({
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "result": result
                    })
                    
                    self.memory_service.add_short_term_tool_result(tool_name, result)
                    self.event_bus.publish("tool_end", {"tool_name": tool_name, "result": result})
                    
                    yield {
                        "type": "tool_end",
                        "tool_name": tool_name,
                        "result": result
                    }
                    
                    # Transition state back to thinking for the next turn
                    self.set_state(AssistantState.THINKING)
                    continue
                else:
                    error_msg = f"Tool '{tool_name}' is not registered."
                    logger.warning(error_msg)
                    if thought:
                        self.memory_service.add_short_term_message("assistant", thought)
                    self.memory_service.add_short_term_tool_result(tool_name, error_msg)
                    
                    yield {
                        "type": "tool_end",
                        "tool_name": tool_name,
                        "result": error_msg
                    }
                    self.set_state(AssistantState.THINKING)
                    continue
            
            # Direct Conversational Response (No tool call)
            response_text = response.get("response", thought)
            self.memory_service.add_short_term_message("assistant", response_text)
            
            # Publish memory write event to the Event Bus asynchronously
            self.event_bus.publish("save_memory", {
                "user_message": user_message,
                "response_text": response_text
            })
            
            self.event_bus.publish("assistant_response", {"response": response_text})
            
            # Check if this successful execution qualifies for a skill save
            clean_user_msg = user_message.lower()
            wants_skill_save = any(keyword in clean_user_msg for keyword in [
                "learn this skill", "save this skill", "save this workflow", 
                "learn a new skill", "save as a skill", "remember this workflow"
            ])
            
            if (wants_skill_save or len(executed_tools) >= 2) and not self.awaiting_skill_save:
                # Generate proposal in background / synchronous context
                proposal = self._generate_skill_proposal(user_message, executed_tools)
                if proposal:
                    self.awaiting_skill_save = True
                    self.pending_skill_data = proposal
                    self.set_state(AssistantState.AWAITING_SKILL_SAVE)
                    
                    yield {
                        "type": "thought",
                        "thought": f"Workflow complete. Proposing to save as skill: '{proposal['name']}'",
                        "tool_name": None,
                        "tool_args": {}
                    }
                    
                    response_text = f"Sir, I have completed this workflow successfully. Would you like me to save this as a permanent skill named '{proposal['name']}'?"
                    self.event_bus.publish("assistant_response", {"response": response_text})
                    
                    yield {
                        "type": "final_response",
                        "response": response_text
                    }
                    return

            yield {
                "type": "final_response",
                "response": response_text
            }
            break
        else:
            logger.warning("Reached maximum turn execution depth without final response.")
            yield {
                "type": "final_response",
                "response": "I executed my tools, but I reached my turn limit before finishing the response."
            }
            
        self.set_state(AssistantState.IDLE)

    def _generate_skill_proposal(self, user_message: str, executed_tools: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Queries the LLM to package the successful workflow into a reusable skill definition."""
        logger.info("[Assistant] Proposing to save successful workflow as a skill.")
        import re
        
        # Construct history of steps
        steps_desc = ""
        for i, step in enumerate(executed_tools):
            steps_desc += f"Step {i+1}: Tool '{step['tool_name']}' was called with args: {json.dumps(step['tool_args'])}\nResult: {step['result']}\n\n"
            
        prompt = f"""You are analyzing a successful execution trace of the Jarvis assistant.
Your goal is to synthesize this sequence of actions into a reusable personal assistant skill.

Original User Intent: "{user_message}"

Executed Workflow Steps:
{steps_desc}

Provide a reusable python function that orchestrates this exact sequence of actions. It must be decorated with `@register_tool` from `tools.registry`.
Also provide the content for a `SKILL.md` markdown file describing how to use this skill, including any parameters.

You MUST respond ONLY with a single JSON object conforming exactly to this schema:
{{
  "skill_name": "reusable_snake_case_name",
  "description": "Short description of what the skill/tool accomplishes.",
  "parameters": {{
    "type": "object",
    "properties": {{
       "optional_arg": {{"type": "string", "description": "..."}}
    }},
    "required": []
  }},
  "python_code": "import time\\nfrom tools.registry import register_tool\\nfrom automation import get_browser_agent\\n\\n@register_tool(\\n    name='reusable_snake_case_name',\\n    description='...',\\n    parameters=...\\n)\\ndef reusable_snake_case_name(**kwargs) -> str:\\n    # write code to execute steps\\n    return 'Success message'",
  "markdown_content": "# Reusable Skill\\nDetailed markdown documentation explaining when to use this skill, parameters, and its internal steps."
}}

Ensure the python code is syntactically valid and handles inputs safely. If no python code is needed (e.g. it is just an instructional/prompt skill), set "python_code" to null or empty string.
"""
        try:
            messages = [
                {"role": "system", "content": "You are a helpful programming assistant that packages successful automation workflows into structured JSON schemas."},
                {"role": "user", "content": prompt}
            ]
            response = self.llm_service.chat(messages)
            name = response.get("skill_name") or response.get("name")
            if name:
                name = re.sub(r'[^\w]', '_', name.lower().strip())
                python_code = response.get("python_code")
                if python_code and "register_tool" not in python_code:
                    python_code = "from tools.registry import register_tool\n" + python_code
                    
                return {
                    "name": name,
                    "description": response.get("description", "Dynamic workflow skill."),
                    "parameters": response.get("parameters", {"type": "object", "properties": {}, "required": []}),
                    "python_code": python_code,
                    "markdown_content": response.get("markdown_content", f"# {name}\nCustom dynamic skill.")
                }
        except Exception as e:
            logger.error(f"[Assistant] Failed to generate skill proposal: {e}")
        return None
            
    def _get_system_prompt(self, relevant_memories: List[str] = None, user_message: str = "") -> str:
        """Generates a dynamic system prompt embedded with the current tool schemas and matching skills."""
        tools_list = self.registry.list_tools()
        tools_formatted = json.dumps(tools_list, indent=2)
        
        memory_context = ""
        if relevant_memories:
            memory_context = "\n\nRELEVANT PAST CONVERSATIONS/CONTEXT:\n" + "\n---\n".join(relevant_memories) + "\n(Use this context to remember facts from past sessions/conversations with the user.)\n"
            
        skills_context = ""
        if user_message:
            try:
                relevant_skills = self.skill_service.retrieve_relevant_skills(user_message, top_k=2)
                if relevant_skills:
                    skills_context = "\n\nRELEVANT SKILLS & PROCEDURAL INSTRUCTIONS:\n"
                    for skill in relevant_skills:
                        skills_context += f"--- SKILL: {skill['name']} ---\nDescription: {skill['description']}\n{skill['body']}\n"
                    skills_context += "(Use these dynamic skill instructions to guide your response or tool orchestration. If a skill defines an associated custom python tool, you can call it just like a regular tool.)\n"
            except Exception as e:
                logger.error(f"[Assistant] Error retrieving relevant skills for prompt context: {e}")
        
        return f"""You are Jarvboi, a highly capable modular personal AI assistant running natively on the user's Windows computer.
You act as JARVIS: a polite, highly capable, and respectful digital butler. Always address the user respectfully (e.g. as "sir" or similar polite butler-like dialogue).
You can control the user's laptop using the provided python automation tools.{memory_context}{skills_context}

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
