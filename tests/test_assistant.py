import os
import sys
import json

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.assistant import Assistant
from tools.registry import registry
from core.llm import OllamaLLM

def test_prompt_tool_embedding():
    """Verifies that the registered desktop tools are dynamically embedded in the system prompt."""
    print("Running: test_prompt_tool_embedding...")
    assistant = Assistant()
    prompt = assistant._get_system_prompt()
    
    assert prompt is not None
    assert "desktop_launch_application" in prompt, "desktop_launch_application is missing from system prompt tools list."
    assert "desktop_focus_window" in prompt, "desktop_focus_window is missing from system prompt tools list."
    assert "desktop_visual_click" in prompt, "desktop_visual_click is missing from system prompt tools list."
    assert "JARVIS:" in prompt, "Jarvis persona instruction is missing from system prompt."
    assert "butler" in prompt, "Jarvis butler instructions are missing."
    
    print(" -> PASS: Prompt dynamically embeds new desktop automation schemas!")

def test_llm_json_clean_and_parse():
    """Verifies that the LLM response cleaning method successfully extracts nested JSON objects from dirty streams."""
    print("Running: test_llm_json_clean_and_parse...")
    ollama_llm = OllamaLLM()
    
    # Case A: JSON inside markdown block
    dirty_text_a = "Here is my final command decision:\n```json\n{\"thought\": \"Testing standard markdown blocks\", \"tool_name\": null, \"tool_args\": {}, \"response\": \"Hello sir.\"}\n```\nHope that helps!"
    parsed_a = ollama_llm._clean_and_parse_json(dirty_text_a)
    assert parsed_a is not None
    assert parsed_a.get("thought") == "Testing standard markdown blocks"
    
    # Case B: Loose text surrounding a raw JSON brace group
    dirty_text_b = "Thinking... {\"thought\": \"Testing braces\", \"tool_name\": \"test_tool\", \"tool_args\": {\"arg\": 123}, \"response\": \"\"} complete."
    parsed_b = ollama_llm._clean_and_parse_json(dirty_text_b)
    assert parsed_b is not None
    assert parsed_b.get("tool_name") == "test_tool"
    assert parsed_b.get("tool_args", {}).get("arg") == 123
    
    print(" -> PASS: LLM JSON parser extraction boundaries fully functional!")

def test_tool_registry():
    """Verifies that all new desktop tools are correctly registered within the global registry schema."""
    print("Running: test_tool_registry...")
    launch_tool = registry.get_tool("desktop_launch_application")
    focus_tool = registry.get_tool("desktop_focus_window")
    click_tool = registry.get_tool("desktop_visual_click")
    
    assert launch_tool is not None, "desktop_launch_application not found in global tool registry."
    assert focus_tool is not None, "desktop_focus_window not found in global tool registry."
    assert click_tool is not None, "desktop_visual_click not found in global tool registry."
    
    # Check parameters schema
    assert "app_name" in launch_tool.parameters["properties"]
    assert "window_title" in focus_tool.parameters["properties"]
    assert "element_description" in click_tool.parameters["properties"]
    
    print(" -> PASS: Automation tools successfully compiled in global registry!")

def run_all():
    """Runs all Assistant unit tests."""
    print("\n--- STARTING ASSISTANT PIPELINE DIAGNOSTIC CHECKS ---")
    try:
        test_prompt_tool_embedding()
        test_llm_json_clean_and_parse()
        test_tool_registry()
        print("CORE COORDINATION STATUS: 100% OPERATIONAL, SIR.")
        return True
    except AssertionError as ae:
        print(f" -> FAIL: AssertionError encountered: {ae}")
        return False
    except Exception as e:
        print(f" -> FAIL: System crash encountered: {e}")
        return False

if __name__ == "__main__":
    run_all()
