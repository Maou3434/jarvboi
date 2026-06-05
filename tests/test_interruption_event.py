import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.event_bus import EventBus
from services.speech_service import SpeechService
from core.assistant import Assistant
from core.state import AssistantState

class TestInterruptionEvent(unittest.TestCase):

    def setUp(self):
        self.event_bus = EventBus()
        
        # Initialize services connected to the same EventBus
        self.speech_service = SpeechService(event_bus=self.event_bus)
        
        self.mock_llm = MagicMock()
        self.mock_memory = MagicMock()
        self.mock_skills = MagicMock()
        self.mock_registry = MagicMock()
        
        # Setup mocks to avoid side effects
        self.mock_memory.get_short_term_history.return_value = []
        self.mock_registry.list_tools.return_value = []
        self.mock_skills.retrieve_relevant_skills.return_value = []
        
        self.assistant = Assistant(
            event_bus=self.event_bus,
            llm_service=self.mock_llm,
            memory_service=self.mock_memory,
            speech_service=self.speech_service,
            tool_registry=self.mock_registry,
            skill_service=self.mock_skills
        )

    def tearDown(self):
        self.speech_service.stop_local_playback()

    @patch("core.assistant.check_ollama_running", return_value=True)
    def test_interruption_stops_audio_and_aborts_loop(self, mock_check):
        """Verifies that publishing an interrupt event stops audio playback and aborts the execution loop."""
        # 1. Setup mock audio playback process
        mock_proc = MagicMock()
        self.speech_service._active_tts_process = mock_proc
        
        # 2. Setup Assistant execution loop to yield a tool call so it continues to next turn
        self.mock_llm.chat.side_effect = [
            {"thought": "First turn thought", "tool_name": "mock_tool", "tool_args": {}},
            {"thought": "Second turn thought", "response": "Done!"}
        ]
        
        mock_tool = MagicMock()
        mock_tool.execute.return_value = "Tool result"
        self.mock_registry.get_tool.return_value = mock_tool
        
        # Run execution loop generator
        execution = self.assistant.execute("do something long")
        
        # Execute the first yields (thought, tool_start, tool_end)
        self.assertEqual(next(execution)["type"], "thought")
        self.assertEqual(next(execution)["type"], "tool_start")
        self.assertEqual(next(execution)["type"], "tool_end")
        
        # State should be TOOL_RUNNING (suspended at tool_end yield before transitioning to thinking)
        self.assertEqual(self.assistant.state, AssistantState.TOOL_RUNNING)
        
        # 3. Trigger interruption event via the Event Bus
        self.event_bus.publish("interrupt")
        
        # Check that interruption flags are set immediately
        self.assertTrue(self.assistant.interrupted)
        self.assertTrue(self.speech_service.interrupted)
        self.assertEqual(self.assistant.state, AssistantState.INTERRUPTED)
        
        # Check that local audio playback was terminated
        mock_proc.terminate.assert_called_once()
        
        # 4. Consume the next step from the execution generator
        # It should loop back, detect interruption and yield a final interrupted response
        fourth_step = next(execution)
        self.assertEqual(fourth_step["type"], "final_response")
        self.assertEqual(fourth_step["response"], "[Interrupted]")
        
        # Generator should be exhausted
        with self.assertRaises(StopIteration):
            next(execution)
            
        # State should reset to IDLE
        self.assertEqual(self.assistant.state, AssistantState.IDLE)

def run_all() -> bool:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestInterruptionEvent)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
