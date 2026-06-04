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
        
        # Check memories table structure
        cursor.execute("PRAGMA table_info(memories)")
        cols = {row["name"] for row in cursor.fetchall()}
        self.assertIn("text", cols)
        self.assertIn("timestamp", cols)
        self.assertIn("embedding_json", cols)
        
        # Check skills table structure
        cursor.execute("PRAGMA table_info(skills)")
        cols_skills = {row["name"] for row in cursor.fetchall()}
        self.assertIn("name", cols_skills)
        self.assertIn("description", cols_skills)
        self.assertIn("parameters_json", cols_skills)
        self.assertIn("python_code", cols_skills)
        conn.close()
        
    def test_add_and_retrieve_memories(self):
        """Verifies memory records, timestamps, and float list embeddings roundtrip correctly."""
        # 1. Add memories
        t1 = 1717416000.0
        t2 = 1717417000.0
        
        success = self.service.add_memory(
            text="User: hello\nJarvis: Hello, sir.",
            timestamp=t1,
            embedding=[0.1, 0.2, 0.3]
        )
        self.assertTrue(success)
        
        # Add another with no embedding
        success2 = self.service.add_memory(
            text="User: offline text\nJarvis: I am offline, sir.",
            timestamp=t2,
            embedding=None
        )
        self.assertTrue(success2)
        
        # 2. Retrieve memories and assert correctness
        memories = self.service.get_memories()
        self.assertEqual(len(memories), 2)
        
        # Should be ordered by timestamp ASC
        m1 = memories[0]
        self.assertEqual(m1["text"], "User: hello\nJarvis: Hello, sir.")
        self.assertEqual(m1["timestamp"], t1)
        self.assertEqual(m1["embedding"], [0.1, 0.2, 0.3])
        
        m2 = memories[1]
        self.assertEqual(m2["text"], "User: offline text\nJarvis: I am offline, sir.")
        self.assertEqual(m2["timestamp"], t2)
        self.assertIsNone(m2["embedding"])
        
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
