import os
import sys
import unittest
import queue
import time
from unittest.mock import MagicMock, patch

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock memory imports before loading memory_service to avoid real vault/graph initialization
mock_vault_cls = MagicMock()
mock_indexer_cls = MagicMock()
mock_graph_cls = MagicMock()
mock_promoter_cls = MagicMock()
mock_retriever_cls = MagicMock()
mock_reflector_cls = MagicMock()

patch_dict = {
    "memory.ObsidianVault": mock_vault_cls,
    "memory.ObsidianIndexer": mock_indexer_cls,
    "memory.ObsidianGraph": mock_graph_cls,
    "memory.MemoryPromoter": mock_promoter_cls,
    "memory.ObsidianRetriever": mock_retriever_cls,
    "memory.MemoryReflector": mock_reflector_cls,
}

for target, mock_obj in patch_dict.items():
    patch(target, mock_obj).start()

# Mock threading.Thread to run the worker loops synchronously or prevent infinite daemon loops during tests
original_thread = patch("threading.Thread").start()

from services.memory_service import MemoryService, EmbeddingClient, ConversationMemory
from config.settings import Settings

class TestMemoryService(unittest.TestCase):

    def setUp(self):
        # Reset mocks
        mock_vault_cls.reset_mock()
        mock_indexer_cls.reset_mock()
        mock_graph_cls.reset_mock()
        mock_promoter_cls.reset_mock()
        mock_retriever_cls.reset_mock()
        mock_reflector_cls.reset_mock()
        original_thread.reset_mock()
        
        # Instantiate service with mocked dependencies
        self.mock_event_bus = MagicMock()
        self.mock_db = MagicMock()
        
        # Prevent threads from automatically starting their worker loops immediately during test instantiations
        # by keeping the thread start mock passive.
        self.service = MemoryService(event_bus=self.mock_event_bus, db_service=self.mock_db)

    def test_service_initialization(self):
        """Verifies MemoryService correctly instantiates components, syncs, and starts background daemon threads."""
        # Check components
        self.assertIsNotNone(self.service.conversation_memory)
        self.assertEqual(mock_graph_cls.return_value.rebuild_graph.call_count, 1)
        self.assertEqual(mock_indexer_cls.return_value.rebuild_index.call_count, 1)
        
        # Check threads (worker loop and reflection loop)
        self.assertEqual(original_thread.call_count, 2)
        
        # Check event bus subscription
        self.mock_event_bus.subscribe.assert_called_once_with("save_memory", self.service._on_save_memory_event)

    def test_conversation_memory_sliding_window(self):
        """Verifies ConversationMemory stores messages and trims them according to max size."""
        mem = ConversationMemory(max_messages=3)
        mem.add_message("user", "msg1")
        mem.add_message("assistant", "msg2")
        mem.add_message("user", "msg3")
        self.assertEqual(len(mem.get_history()), 3)
        
        # Adding a fourth message should trim the first one (msg1)
        mem.add_message("assistant", "msg4")
        self.assertEqual(len(mem.get_history()), 3)
        self.assertEqual(mem.get_history()[0]["content"], "msg2")
        
        # Adding system message and trimming checks
        mem.clear()
        self.assertEqual(len(mem.get_history()), 0)

    def test_event_bus_handler_puts_queue(self):
        """Verifies that the event bus callback puts tasks in the queue async."""
        self.service.queue = MagicMock()
        event_data = {
            "user_message": "User query",
            "response_text": "Assistant reply"
        }
        self.service._on_save_memory_event(event_data)
        self.service.queue.put.assert_called_once_with(("User query", "Assistant reply"))

    def test_worker_loop_iteration(self):
        """Verifies that the worker thread pulls from the queue and calls promotion & indexing."""
        # Create a real queue for testing the iteration logic
        test_queue = queue.Queue()
        self.service.queue = test_queue
        
        # Feed one turn
        test_queue.put(("Query", "Reply"))
        # Feed None to break the loop
        test_queue.put(None)
        
        # Run worker loop execution
        self.service._worker_loop()
        
        # Verify promoter and rebuild are called
        self.service.promoter.promote_conversation_turn.assert_called_once_with("Query", "Reply")
        self.assertEqual(self.service.graph.rebuild_graph.call_count, 2) # 1 from init + 1 from worker
        self.assertEqual(self.service.indexer.rebuild_index.call_count, 2) # 1 from init + 1 from worker
        self.assertEqual(test_queue.qsize(), 0)

    @patch("urllib.request.urlopen")
    @patch("urllib.request.Request")
    def test_embedding_client_gemini_routing(self, mock_request_cls, mock_urlopen):
        """Verifies EmbeddingClient routes to Gemini HTTP API when set to gemini."""
        Settings.LLM_PROVIDER = "gemini"
        Settings.GEMINI_API_KEY = "test-api-key"
        
        # Mock successful JSON response from Gemini
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"embedding": {"values": [0.1, 0.2, 0.3]}}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        emb = EmbeddingClient.get_embedding("hello world")
        self.assertEqual(emb, [0.1, 0.2, 0.3])
        
        # Check request URL
        args, kwargs = mock_request_cls.call_args
        self.assertIn("generativelanguage.googleapis.com", args[0])

    @patch("urllib.request.urlopen")
    def test_embedding_client_ollama_routing(self, mock_urlopen):
        """Verifies EmbeddingClient routes to Ollama client library when set to ollama."""
        Settings.LLM_PROVIDER = "ollama"
        Settings.OLLAMA_HOST = "http://localhost:11434"
        
        # Mock Ollama host check passing
        mock_urlopen.return_value.__enter__.return_value = MagicMock()
        
        # Mock local import of ollama module and call
        mock_ollama = MagicMock()
        mock_ollama.embeddings.return_value = {"embedding": [0.4, 0.5, 0.6]}
        
        with patch.dict(sys.modules, {"ollama": mock_ollama}):
            emb = EmbeddingClient.get_embedding("test query")
            self.assertEqual(emb, [0.4, 0.5, 0.6])
            mock_ollama.embeddings.assert_called_once_with(model="nomic-embed-text", prompt="test query")

    def test_retrieve_long_term_context(self):
        """Verifies long term context builder calls retriever and formats context string."""
        self.service.retriever.retrieve.return_value = [{"title": "Concept"}]
        self.service.retriever.build_context.return_value = "Retrieved Context Info"
        
        context = self.service.retrieve_long_term_context("query string")
        self.assertEqual(context, ["Retrieved Context Info"])
        self.service.retriever.retrieve.assert_called_once_with("query string", top_k=3)
        self.service.retriever.build_context.assert_called_once_with("query string", [{"title": "Concept"}])

def run_all() -> bool:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMemoryService)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
