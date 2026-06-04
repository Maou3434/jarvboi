import os
import shutil
import sys
import unittest

# Ensure project root resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.skill_service import SkillService, parse_yaml_fallback
from tools.registry import registry

class TestSkillService(unittest.TestCase):
    
    def setUp(self):
        # Create a isolated test skills directory
        self.test_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "test_skills_temp"
        )
        os.makedirs(self.test_dir, exist_ok=True)
        self.service = SkillService(skills_dir=self.test_dir)
        
    def tearDown(self):
        # Clean up temporary test skills directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            
    def test_yaml_frontmatter_fallback_parser(self):
        """Verifies the custom fallback parser correctly resolves YAML strings into dictionaries."""
        yaml_text = """
name: test_yaml_skill
description: "A test description of this custom skill."
category: automation
parameters:
  type: object
  properties:
    query:
      type: string
      description: "Search search phrase"
    count:
      type: integer
  required: [query]
"""
        meta = parse_yaml_fallback(yaml_text)
        self.assertEqual(meta.get("name"), "test_yaml_skill")
        self.assertEqual(meta.get("description"), "A test description of this custom skill.")
        self.assertEqual(meta.get("category"), "automation")
        
        params = meta.get("parameters", {})
        self.assertEqual(params.get("type"), "object")
        self.assertEqual(params.get("properties", {}).get("query", {}).get("type"), "string")
        self.assertEqual(params.get("properties", {}).get("count", {}).get("type"), "integer")
        self.assertEqual(params.get("required"), ["query"])
        
    def test_create_and_load_prompt_skill(self):
        """Verifies instructional skills (prompt-only) can be successfully written and parsed."""
        success = self.service.create_skill(
            name="test_prompt_skill",
            description="Allows Jarvboi to perform test task.",
            parameters=None,
            python_code=None,
            markdown_content="# Test Instructions\nFollow these guidelines:\n1. Execute action\n2. Report success."
        )
        self.assertTrue(success)
        
        # Verify files on disk
        skill_folder = os.path.join(self.test_dir, "test_prompt_skill")
        self.assertTrue(os.path.exists(skill_folder))
        self.assertTrue(os.path.exists(os.path.join(skill_folder, "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(skill_folder, "tool.py")))
        
        # Re-initialize to verify scanning
        new_service = SkillService(skills_dir=self.test_dir)
        self.assertIn("test_prompt_skill", new_service.skills)
        meta = new_service.skills["test_prompt_skill"]
        self.assertEqual(meta["description"], "Allows Jarvboi to perform test task.")
        self.assertEqual(meta["category"], "instructions")
        self.assertIn("Execute action", meta["body"])
        
    def test_create_and_load_action_skill(self):
        """Verifies executable skills with python_code are written, dynamically imported, and registered."""
        python_code = """
import time
from tools.registry import register_tool

@register_tool(
    name="test_dynamic_exec_tool",
    description="A test dynamic executor tool.",
    parameters={
        "type": "object",
        "properties": {
            "val": {"type": "string", "description": "a value"}
        },
        "required": ["val"]
    }
)
def test_dynamic_exec_tool(val: str) -> str:
    return f"Test dynamic result: {val}"
"""
        success = self.service.create_skill(
            name="test_dynamic_exec_tool",
            description="Test dynamic skill executor.",
            parameters={
                "type": "object",
                "properties": {
                    "val": {"type": "string", "description": "a value"}
                },
                "required": ["val"]
            },
            python_code=python_code,
            markdown_content="# Executable Tool\nDoes a test run."
        )
        self.assertTrue(success)
        
        # Verify tool registration in global registry
        registered_tool = registry.get_tool("test_dynamic_exec_tool")
        self.assertIsNotNone(registered_tool)
        self.assertEqual(registered_tool.description, "Test dynamic skill executor.")
        
        # Execute tool to verify functional binding
        result = registered_tool.execute(val="Hello World")
        self.assertEqual(result, "Test dynamic result: Hello World")
        
    def test_similarity_search(self):
        """Verifies dynamic skill discovery retrieves relevant skills using Jaccard checks."""
        self.service.create_skill(
            name="open_spotify_music",
            description="Launches spotify and plays user music tracks.",
            parameters=None,
            python_code=None,
            markdown_content="Guides for launching spotify desktop app."
        )
        self.service.create_skill(
            name="open_notepad_document",
            description="Launches notepad text editor and opens document.",
            parameters=None,
            python_code=None,
            markdown_content="Guides for writing notepad editor files."
        )
        
        # Search for spotify
        results = self.service.retrieve_relevant_skills("can you play some music on spotify", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "open_spotify_music")
        
        # Search for notepad
        results2 = self.service.retrieve_relevant_skills("open note editor notepad please", top_k=1)
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0]["name"], "open_notepad_document")

def run_all():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSkillService)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
