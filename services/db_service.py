import os
import json
import time
import sqlite3
from typing import List, Dict, Any, Optional
from config.settings import Settings
from utils.logger import logger

class DbService:
    """Thread-safe SQLite database manager for Jarvboi, handling relational storage
    for conversation memory logs and dynamically created skills.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, Settings.DATABASE_PATH)
            
        self.db_path = db_path
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize schema
        self._create_tables()
        
    def _get_connection(self) -> sqlite3.Connection:
        """Creates and returns a new sqlite3 database connection with Row factories enabled."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn
        
    def _create_tables(self):
        """Creates the memories and skills tables if they do not already exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Conversational vector memories table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        text TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        embedding_json TEXT
                    )
                """)
                
                # Skills table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS skills (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT,
                        category TEXT,
                        parameters_json TEXT,
                        markdown_content TEXT,
                        python_code TEXT,
                        timestamp REAL NOT NULL
                    )
                """)
                
                conn.commit()
                logger.info(f"[DbService] Database initialized successfully at {self.db_path}")
        except Exception as e:
            logger.error(f"[DbService] Failed to initialize database: {e}")
            
    # --- memories CRUD operations ---
    
    def add_memory(self, text: str, timestamp: float, embedding: Optional[List[float]]) -> bool:
        """Inserts a conversation log context record with optional embedding coordinates."""
        try:
            embedding_json = json.dumps(embedding) if embedding is not None else None
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO memories (text, timestamp, embedding_json) VALUES (?, ?, ?)",
                    (text, timestamp, embedding_json)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[DbService] Error adding memory record: {e}")
            return False
            
    def get_memories(self) -> List[Dict[str, Any]]:
        """Retrieves all memory log records from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT text, timestamp, embedding_json FROM memories ORDER BY timestamp ASC")
                rows = cursor.fetchall()
                
            result = []
            for row in rows:
                emb = None
                if row["embedding_json"]:
                    try:
                        emb = json.loads(row["embedding_json"])
                    except Exception:
                        pass
                result.append({
                    "text": row["text"],
                    "timestamp": row["timestamp"],
                    "embedding": emb
                })
            return result
        except Exception as e:
            logger.error(f"[DbService] Error retrieving memory records: {e}")
            return []
            
    # --- skills CRUD operations ---
    
    def add_skill(self, name: str, description: str, category: str, parameters: Dict[str, Any], markdown_content: str, python_code: Optional[str]) -> bool:
        """Saves or updates a custom skill record in the database."""
        try:
            parameters_json = json.dumps(parameters) if parameters else "{}"
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO skills 
                    (name, description, category, parameters_json, markdown_content, python_code, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, description, category, parameters_json, markdown_content, python_code, time.time())
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[DbService] Error saving skill '{name}' to DB: {e}")
            return False
            
    def get_skills(self) -> List[Dict[str, Any]]:
        """Retrieves all skill records from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT name, description, category, parameters_json, markdown_content, python_code FROM skills")
                rows = cursor.fetchall()
                
            result = []
            for row in rows:
                params = {}
                if row["parameters_json"]:
                    try:
                        params = json.loads(row["parameters_json"])
                    except Exception:
                        pass
                result.append({
                    "name": row["name"],
                    "description": row["description"],
                    "category": row["category"],
                    "parameters": params,
                    "markdown_content": row["markdown_content"],
                    "python_code": row["python_code"]
                })
            return result
        except Exception as e:
            logger.error(f"[DbService] Error retrieving skill records: {e}")
            return []
            
    def delete_skill(self, name: str) -> bool:
        """Removes a skill record by name."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM skills WHERE name = ?", (name,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[DbService] Error deleting skill '{name}': {e}")
            return False
