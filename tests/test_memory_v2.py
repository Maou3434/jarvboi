import os
import sys
import shutil
import unittest
import unittest.mock
import time

# Ensure project root resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any, List, Optional
from memory.vault import ObsidianVault
from memory.scorer import ImportanceScorer
from memory.extractor import MemoryExtractor
from memory.linker import ObsidianLinker
from memory.promoter import MemoryPromoter
from memory.indexer import ObsidianIndexer
from memory.graph import ObsidianGraph
from memory.retriever import ObsidianRetriever
from memory.reflector import MemoryReflector
from memory.models import CandidateMemory

class MockLLM:
    """Mock LLM Service returning pre-programmed JSON payloads for testing."""
    def __init__(self, return_value: Dict[str, Any]):
        self.return_value = return_value
        
    def generate_json(self, messages: List[Dict[str, str]], response_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.return_value

class TestMemorySystemV2(unittest.TestCase):
    
    def setUp(self):
        # Establish temporary directories for vault and Qdrant db to isolate tests
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_obsidian_vault")
        self.qdrant_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_qdrant_db")
        
        self.vault = ObsidianVault(vault_dir=self.test_dir)
        self.scorer = ImportanceScorer()
        self.linker = ObsidianLinker()
        
    def tearDown(self):
        # Clean up temporary test directories
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists(self.qdrant_dir):
            shutil.rmtree(self.qdrant_dir)
            
    def test_vault_init(self):
        """Verifies that all vault subfolders are initialized correctly."""
        self.assertTrue(os.path.exists(self.test_dir))
        for cat in ["People", "Projects", "Concepts", "Daily", "Meetings", "Procedures", "Archive"]:
            self.assertTrue(os.path.exists(os.path.join(self.test_dir, cat)))
            
    def test_scorer_calculation(self):
        """Verifies importance calculation and route mapping."""
        # Test discard threshold (< 0.3)
        mem1 = CandidateMemory("Opened Chrome", "Daily", "General", relevance=0.1, recurrence=0.1, novelty=0.1, user_signal=0.1)
        score1, route1 = self.scorer.score_and_route(mem1)
        self.assertLess(score1, 0.30)
        self.assertEqual(route1, "discard")
        
        # Test daily-only threshold (0.30 - 0.70)
        mem2 = CandidateMemory("Implemented memory updates", "Daily", "General", relevance=0.6, recurrence=0.5, novelty=0.4, user_signal=0.3)
        score2, route2 = self.scorer.score_and_route(mem2)
        # 0.35*0.6 + 0.25*0.5 + 0.20*0.4 + 0.20*0.3 = 0.21 + 0.125 + 0.08 + 0.06 = 0.475
        self.assertAlmostEqual(score2, 0.475)
        self.assertEqual(route2, "daily_only")
        
        # Test promote threshold (> 0.70)
        mem3 = CandidateMemory("Abi prefers Rust programming", "People", "Abi", relevance=0.9, recurrence=0.8, novelty=0.9, user_signal=0.9)
        score3, route3 = self.scorer.score_and_route(mem3)
        self.assertGreater(score3, 0.70)
        self.assertEqual(route3, "promote")
        
    def test_extractor_mock(self):
        """Verifies extractor parses LLM response into candidate memory dataclasses."""
        mock_response = {
            "candidates": [
                {
                    "fact": "Abi works on Jarvis project",
                    "category": "People",
                    "entity_name": "Abi",
                    "relevance": 0.8,
                    "recurrence": 0.6,
                    "novelty": 0.5,
                    "user_signal": 0.7,
                    "memory_type": "semantic",
                    "extra_data": {}
                }
            ]
        }
        mock_llm = MockLLM(mock_response)
        extractor = MemoryExtractor(mock_llm)
        
        memories = extractor.extract_memories("I work on Jarvis", "Understood, sir.")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].fact, "Abi works on Jarvis project")
        self.assertEqual(memories[0].category, "People")
        self.assertEqual(memories[0].entity_name, "Abi")
        self.assertEqual(memories[0].user_signal, 0.7)
        
    def test_conflict_handling_block(self):
        """Verifies conflict section is generated correctly on contradiction."""
        self.vault.write_note("People", "Abi", {}, "# Abi\n\n## Facts & Details\n- Likes Python")
        
        # Manually invoke add_conflict
        self.vault.add_conflict("People", "Abi", "Likes Python", "Likes Rust")
        
        metadata, body = self.vault.read_note("People", "Abi")
        self.assertIn("## Conflicting Information", body)
        self.assertIn("- Likes Python (older)", body)
        self.assertIn("- Likes Rust (newer)", body)
        self.assertIn("Status: unresolved", body)
        
    def test_linker_auto_linking(self):
        """Verifies note text is linked to existing entities in vault, sorting by length."""
        notes = [
            {"title": "Abi", "category": "People", "metadata": {}, "body": ""},
            {"title": "Jarvis", "category": "Projects", "metadata": {}, "body": ""},
            {"title": "Memory System", "category": "Concepts", "metadata": {}, "body": ""}
        ]
        
        text = "Abi implemented a Memory System in Jarvis."
        linked = self.linker.auto_link_text(text, notes)
        
        # Verify brackets added
        self.assertIn("[[Abi]]", linked)
        self.assertIn("[[Jarvis]]", linked)
        self.assertIn("[[Memory System]]", linked)
        
    def test_networkx_graph(self):
        """Verifies link parsing and graph construction via NetworkX."""
        # Create some notes with bracket links
        self.vault.write_note("Projects", "Jarvis", {}, "# Jarvis\n\n- Part of [[Memory System]]\n- Created by [[Abi]]")
        self.vault.write_note("People", "Abi", {}, "# Abi\n\n- Creator of [[Jarvis]]")
        self.vault.write_note("Concepts", "Memory System", {}, "# Memory System\n\n- Uses embeddings")
        
        graph = ObsidianGraph()
        graph.rebuild_graph(self.vault)
        
        # Test nodes and edges
        self.assertTrue(graph.graph.has_node("Jarvis"))
        self.assertTrue(graph.graph.has_node("Abi"))
        self.assertTrue(graph.graph.has_node("Memory System"))
        
        # Edge test
        self.assertTrue(graph.graph.has_edge("Jarvis", "Memory System"))
        self.assertTrue(graph.graph.has_edge("Jarvis", "Abi"))
        self.assertTrue(graph.graph.has_edge("Abi", "Jarvis"))
        
        # Neighbors (all connected undirected nodes)
        neighbors = graph.get_connected_notes("Jarvis")
        self.assertIn("Abi", neighbors)
        self.assertIn("Memory System", neighbors)
        
    def test_reflector_decay(self):
        """Verifies that the reflector runs decay calculation and moves stale notes to Archive."""
        metadata = {
            "created_at": time.time() - 10 * 86400, # 10 days old
            "last_accessed": time.time() - 10 * 86400,
            "times_retrieved": 0,
            "importance": 0.24 # will drop below 0.20 archive threshold under 0.05 decay
        }
        self.vault.write_note("People", "Abi", metadata, "# Abi\n- Prefers Python")
        
        # Initialize reflector (mock LLM for synthesis)
        reflector = MemoryReflector(
            vault=self.vault,
            indexer=None, # not testing indexing rebuild here
            graph=None,
            llm_service=MockLLM({"insights": []}),
            decay_rate=0.05,
            archive_threshold=0.20
        )
        
        # Run decay & archive portion
        reflector._apply_decay_and_archive(time.time())
        
        # Should be moved to Archive folder
        self.assertFalse(self.vault.note_exists("People", "Abi"))
        self.assertTrue(self.vault.note_exists("Archive", "Abi"))
        
        # Metadata check in Archive
        archived_meta, body = self.vault.read_note("Archive", "Abi")
        self.assertEqual(archived_meta.get("category"), "Archive")
        self.assertLess(archived_meta.get("importance"), 0.20)

    @unittest.mock.patch("services.memory_service.EmbeddingClient.get_embedding")
    def test_indexer_and_retriever(self, mock_embed):
        """Verifies serverless Qdrant indexing, incremental rebuilds, and multi-factor context assembly."""
        mock_embed.return_value = [0.1] * 768
        
        # Initialize Indexer using temp qdrant path
        indexer = ObsidianIndexer(db_path=self.qdrant_dir)
        try:
            # Create notes in the vault
            self.vault.write_note("Projects", "Jarvis", {"importance": 0.8}, "# Jarvis\n\nSome content about the AI assistant project.")
            self.vault.write_note("People", "Abi", {"importance": 0.9}, "# Abi\n\nSome facts about Abi.")
            
            # Rebuild index
            indexer.rebuild_index(self.vault)
            
            # Test index search
            hits = indexer.search([0.1]*768, top_k=2)
            self.assertEqual(len(hits), 2)
            self.assertIn(hits[0]["title"], ["Jarvis", "Abi"])
            
            # Test graph + retriever expansion
            graph = ObsidianGraph()
            graph.rebuild_graph(self.vault)
            
            retriever = ObsidianRetriever(self.vault, indexer, graph)
            ranked = retriever.retrieve("Jarvis assistant", top_k=1)
            self.assertGreater(len(ranked), 0)
            self.assertEqual(ranked[0]["title"], hits[0]["title"]) # top match
            
            # Build context
            context = retriever.build_context("Jarvis assistant", ranked)
            self.assertIn("NOTE:", context)
        finally:
            indexer.close()

def run_all() -> bool:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMemorySystemV2)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
