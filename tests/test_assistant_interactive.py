import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.assistant import Assistant
from core.state import AssistantState

class TestAssistantInteractive(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MagicMock()
        self.mock_memory = MagicMock()
        self.mock_memory.get_short_term_history.return_value = []
        self.mock_speech = MagicMock()
        self.mock_registry = MagicMock()
        self.mock_registry.list_tools.return_value = []
        self.mock_skills = MagicMock()
        self.mock_skills.retrieve_relevant_skills.return_value = []
        self.mock_event_bus = MagicMock()
        
        self.assistant = Assistant(
            event_bus=self.mock_event_bus,
            llm_service=self.mock_llm,
            memory_service=self.mock_memory,
            speech_service=self.mock_speech,
            tool_registry=self.mock_registry,
            skill_service=self.mock_skills
        )
        # Mock default provider flags
        self.assistant.preferred_provider = "ollama"
        self.assistant.has_gemini = True

    @patch("core.assistant.check_ollama_running", return_value=False)
    def test_ollama_offline_initiates_wsl_prompt(self, mock_check):
        """Verifies that if local Ollama is offline, the user is prompted to start it in WSL."""
        steps = list(self.assistant.execute("hello"))
        
        self.assertTrue(self.assistant.awaiting_ollama_start)
        # Verify first step thought and final response
        self.assertEqual(steps[0]["type"], "thought")
        self.assertIn("Ollama service is not running", steps[0]["thought"])
        self.assertEqual(steps[1]["type"], "final_response")
        self.assertIn("Would you like me to start it in WSL?", steps[1]["response"])

    @patch("subprocess.Popen")
    @patch("time.sleep")
    @patch("core.assistant.check_ollama_running")
    def test_ollama_wsl_start_confirmation(self, mock_check, mock_sleep, mock_popen):
        """Verifies that affirming the WSL start prompt launches Ollama in WSL and switches provider."""
        self.assistant.awaiting_ollama_start = True
        
        # First check (inside executive loop) returns False, second check (after start) returns True
        mock_check.side_effect = [True]
        
        steps = list(self.assistant.execute("yes"))
        
        # Verify WSL boot trigger
        mock_popen.assert_called_once_with(["wsl", "ollama", "serve"], stdout=unittest.mock.ANY, stderr=unittest.mock.ANY)
        mock_sleep.assert_called_once_with(4.0)
        self.mock_llm.switch_to_ollama.assert_called_once()
        self.assertFalse(self.assistant.awaiting_ollama_start)
        
        # Verify response messages
        final_responses = [s["response"] for s in steps if s.get("type") == "final_response"]
        self.assertIn("Starting the Ollama service in WSL now.", final_responses[0])
        self.assertIn("The Ollama service is now online in WSL and ready for use", final_responses[1])

    @patch("core.assistant.check_ollama_running", return_value=False)
    def test_ollama_decline_triggers_gemini_switch_prompt(self, mock_check):
        """Verifies that declining the WSL start prompts switching to Gemini if available."""
        self.assistant.awaiting_ollama_start = True
        
        steps = list(self.assistant.execute("no"))
        
        self.assertFalse(self.assistant.awaiting_ollama_start)
        self.assertTrue(self.assistant.awaiting_gemini_switch)
        
        final_responses = [s["response"] for s in steps if s.get("type") == "final_response"]
        self.assertIn("Would you like me to switch to Gemini instead?", final_responses[0])

    def test_gemini_switch_confirmation(self):
        """Verifies that confirming the Gemini switch updates the active provider."""
        self.assistant.awaiting_gemini_switch = True
        
        steps = list(self.assistant.execute("yes"))
        
        self.mock_llm.switch_to_gemini.assert_called_once()
        self.assertEqual(self.assistant.preferred_provider, "gemini")
        self.assertFalse(self.assistant.awaiting_gemini_switch)
        
        final_responses = [s["response"] for s in steps if s.get("type") == "final_response"]
        self.assertIn("I have switched our LLM provider to Gemini.", final_responses[0])

    @patch("core.assistant.check_ollama_running", return_value=True)
    def test_skill_save_proposal_and_confirm(self, mock_check):
        """Verifies that completing a workflow with 2+ tool calls prompts a skill proposal."""
        # Mock LLM behavior to return thoughts and responses
        self.mock_llm.chat.side_effect = [
            {"thought": "Thinking tool 1", "tool_name": "t1", "tool_args": {}},
            {"thought": "Thinking tool 2", "tool_name": "t2", "tool_args": {}},
            {"thought": "Final answer", "response": "Done!"}
        ]
        
        # Mock tools in registry
        mock_t1 = MagicMock()
        mock_t2 = MagicMock()
        mock_t1.execute.return_value = "Result 1"
        mock_t2.execute.return_value = "Result 2"
        self.mock_registry.get_tool.side_effect = lambda name: mock_t1 if name == "t1" else mock_t2
        
        # Mock skill proposal generation
        proposal = {
            "name": "test_macro_skill",
            "description": "Custom test macro",
            "parameters": {},
            "python_code": "def test_macro_skill(): pass",
            "markdown_content": "# Macro"
        }
        
        with patch.object(self.assistant, "_generate_skill_proposal", return_value=proposal):
            steps = list(self.assistant.execute("run macro please"))
            
            self.assertTrue(self.assistant.awaiting_skill_save)
            self.assertEqual(self.assistant.pending_skill_data, proposal)
            self.assertEqual(self.assistant.state, AssistantState.AWAITING_SKILL_SAVE)
            
            # Confirming the skill save
            self.mock_skills.create_skill.return_value = True
            confirm_steps = list(self.assistant.execute("yes"))
            
            self.mock_skills.create_skill.assert_called_once_with(
                name="test_macro_skill",
                description="Custom test macro",
                parameters={},
                python_code="def test_macro_skill(): pass",
                markdown_content="# Macro"
            )
            self.assertFalse(self.assistant.awaiting_skill_save)
            
            # Confirm response yielded successfully
            final_responses = [s["response"] for s in confirm_steps if s.get("type") == "final_response"]
            self.assertIn("I have saved and loaded the skill 'test_macro_skill'.", final_responses[0])

    @patch("core.assistant.check_ollama_running", return_value=True)
    def test_rag_context_injection(self, mock_check):
        """Verifies that relevant long-term memories are retrieved and injected into the prompt."""
        self.mock_memory.retrieve_long_term_context.return_value = ["User: I prefer dark theme.\nJarvis: Noted, sir."]
        self.mock_llm.chat.return_value = {"thought": "Hello", "response": "Hello sir."}
        
        list(self.assistant.execute("hi"))
        
        # Verify retrieve_long_term_context was queried with user query
        self.mock_memory.retrieve_long_term_context.assert_called_once_with("hi", top_k=3)
        
        # Verify context is in the LLM chat input system prompt
        called_messages = self.mock_llm.chat.call_args[0][0]
        system_msg = called_messages[0]["content"]
        self.assertIn("RELEVANT PAST CONVERSATIONS/CONTEXT", system_msg)
        self.assertIn("I prefer dark theme", system_msg)

def run_all() -> bool:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAssistantInteractive)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
