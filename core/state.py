from enum import Enum

class AssistantState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    TOOL_RUNNING = "tool_running"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    AWAITING_SKILL_SAVE = "awaiting_skill_save"

    def to_ui_status(self) -> str:
        """Maps detailed internal assistant states to status strings recognized by the HUD UI."""
        if self in (AssistantState.THINKING, AssistantState.TOOL_RUNNING, AssistantState.AWAITING_SKILL_SAVE):
            return "processing"
        return self.value
