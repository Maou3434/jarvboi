from typing import List, Dict

class ConversationMemory:
    """Manages the in-memory chat history for the assistant conversation."""
    
    def __init__(self, max_messages: int = 40):
        self.messages: List[Dict[str, str]] = []
        self.max_messages = max_messages
        
    def add_message(self, role: str, content: str):
        """Adds a standard message (system, user, or assistant) to memory."""
        self.messages.append({
            "role": role,
            "content": content
        })
        self._trim_memory()
        
    def add_tool_result(self, tool_name: str, result: str):
        """Adds the tool execution output back to the conversation as a system/user update.
        
        Note: Some local models respond better to a structured 'system' or 'user' message
        showing the tool output rather than the official 'tool' role if they lack native
        tool calling capabilities. We will structure it as a system message.
        """
        self.messages.append({
            "role": "system",
            "content": f"TOOL EXECUTION RESULT [{tool_name}]:\n{result}"
        })
        self._trim_memory()
        
    def get_history(self) -> List[Dict[str, str]]:
        """Returns the full conversation log."""
        return self.messages
        
    def clear(self):
        """Clears all stored conversation logs except system prompts."""
        system_messages = [msg for msg in self.messages if msg["role"] == "system" and "TOOL EXECUTION" not in msg["content"]]
        self.messages = system_messages
        
    def _trim_memory(self):
        """Maintains the conversation history within maximum bounds."""
        if len(self.messages) > self.max_messages:
            # Preserve system instructions at index 0 if it's there
            has_system = len(self.messages) > 0 and self.messages[0]["role"] == "system"
            
            if has_system:
                sys_msg = self.messages[0]
                # Slice the remaining, leaving room for system instruction
                self.messages = [sys_msg] + self.messages[-(self.max_messages - 1):]
            else:
                self.messages = self.messages[-self.max_messages:]
