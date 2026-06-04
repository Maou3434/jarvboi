import os
import sys
import unittest
import tempfile

# Ensure project root resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.db_service import DbService

class TestDbService(unittest.TestCase):
    
    def setUp(self):
        # Create a temporary file path for isolated SQLite test DB
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.service = DbService(db_path=self.db_path)
        
    def tearDown(self):
        # Clean up temporary database file
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
                
    def test_database_table_initialization(self):
        """Verifies that the database establishes tables cleanly upon startup."""
        conn = self.service._get_connection()
        cursor = conn.cursor()
        
        # Check skills table structure
        cursor.execute("PRAGMA table_info(skills)")
        cols_skills = {row["name"] for row in cursor.fetchall()}
        self.assertIn("name", cols_skills)
        self.assertIn("description", cols_skills)
        self.assertIn("parameters_json", cols_skills)
        self.assertIn("python_code", cols_skills)
        conn.close()
        

    def test_add_retrieve_and_delete_skills(self):
        """Verifies skill metadata, parameter schemas, code, and deletions roundtrip correctly."""
        name = "play_jazz_music"
        desc = "Opens browser to play jazz music."
        cat = "automation"
        params = {
            "type": "object",
            "properties": {
                "volume": {"type": "integer"}
            },
            "required": ["volume"]
        }
        md = "# Play Jazz\nPlays sweet tunes."
        code = "def play_jazz_music(): pass"
        
        # 1. Add skill
        success = self.service.add_skill(
            name=name,
            description=desc,
            category=cat,
            parameters=params,
            markdown_content=md,
            python_code=code
        )
        self.assertTrue(success)
        
        # 2. Retrieve skill and verify
        skills = self.service.get_skills()
        self.assertEqual(len(skills), 1)
        
        s = skills[0]
        self.assertEqual(s["name"], name)
        self.assertEqual(s["description"], desc)
        self.assertEqual(s["category"], cat)
        self.assertEqual(s["parameters"], params)
        self.assertEqual(s["markdown_content"], md)
        self.assertEqual(s["python_code"], code)
        
        # 3. Delete skill and verify
        delete_success = self.service.delete_skill(name)
        self.assertTrue(delete_success)
        
        skills_post_delete = self.service.get_skills()
        self.assertEqual(len(skills_post_delete), 0)

def run_all():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDbService)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
