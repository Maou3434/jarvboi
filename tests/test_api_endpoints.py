import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import json

import threading
import sqlite3

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch Obsidian indexer, graph rebuilds, and QdrantClient to avoid heavy startup times and locks
patch("memory.indexer.ObsidianIndexer.rebuild_index", MagicMock()).start()
patch("memory.graph.ObsidianGraph.rebuild_graph", MagicMock()).start()
patch("memory.indexer.QdrantClient", MagicMock()).start()

# Patch sqlite3.connect globally to run in-memory to prevent file locks
patch("sqlite3.connect", side_effect=lambda *args, **kwargs: sqlite3.connect(":memory:")).start()

# Selectively mock the background voice loop thread to prevent it from starting during tests
original_thread = threading.Thread
def mock_thread_init(*args, **kwargs):
    target = kwargs.get("target") or (args[1] if len(args) > 1 else None)
    if target and getattr(target, "__name__", None) == "background_voice_loop":
        return MagicMock()
    return original_thread(*args, **kwargs)

patch("threading.Thread", side_effect=mock_thread_init).start()

# Import api module first to mock global variables before lifespan starts
import api
from fastapi.testclient import TestClient

# Mock SpeechService methods to avoid background thread mic calibration/listening errors
api.speech_service.calibrate_mic = MagicMock()

def mock_listen(*args, **kwargs):
    import time
    time.sleep(0.2)
    return None

api.speech_service.listen_mic = MagicMock(side_effect=mock_listen)
api.speech_service.speak = MagicMock()

# Mock memory service
api.memory_service.clear = MagicMock()

class TestApiEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(api.app)
        
        # Reset mocks
        api.memory_service.clear.reset_mock()
        api.speech_service.calibrate_mic.reset_mock()
        api.speech_service.listen_mic.reset_mock()
        api.speech_service.speak.reset_mock()

    def test_status_endpoint(self):
        """Verifies GET /status retrieves current service info."""
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "online")
        self.assertEqual(data.get("model"), api.llm_service.provider)

    def test_chat_endpoint(self):
        """Verifies POST /chat triggers non-streaming query execution."""
        mock_execute = MagicMock(return_value=[
            {"type": "thought", "thought": "Thought text"},
            {"type": "final_response", "response": "Response text"}
        ])
        
        with patch.object(api.assistant, "execute", mock_execute):
            response = self.client.post("/chat", json={"message": "hello jarvis"})
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            self.assertEqual(data.get("response"), "Response text")
            self.assertEqual(len(data.get("steps")), 2)
            mock_execute.assert_called_once_with("hello jarvis")

    def test_websocket_chat_message(self):
        """Verifies WebSocket accepts messages, yields execution steps and handles 'clear' instruction."""
        print("[TEST DEBUG] Starting test_websocket_chat_message")
        mock_execute = MagicMock(return_value=[
            {"type": "thought", "thought": "WS thought"},
            {"type": "final_response", "response": "WS response"}
        ])
        
        # Life cycle wrapper to trigger lifespan startup/shutdown
        print("[TEST DEBUG] Connecting websocket...")
        with self.client.websocket_connect("/ws/chat") as websocket:
            print("[TEST DEBUG] Connected. Sending message 'hi'...")
            with patch.object(api.assistant, "execute", mock_execute):
                websocket.send_text(json.dumps({"message": "hi"}))
                
                # Receive yields
                print("[TEST DEBUG] Waiting to receive step 1...")
                step1 = json.loads(websocket.receive_text())
                print(f"[TEST DEBUG] Received step 1: {step1}")
                self.assertEqual(step1["type"], "thought")
                self.assertEqual(step1["thought"], "WS thought")
                
                print("[TEST DEBUG] Waiting to receive step 2...")
                step2 = json.loads(websocket.receive_text())
                print(f"[TEST DEBUG] Received step 2: {step2}")
                self.assertEqual(step2["type"], "final_response")
                self.assertEqual(step2["response"], "WS response")
                
            # Send 'clear' memory console command
            print("[TEST DEBUG] Sending 'clear'...")
            websocket.send_text("clear")
            print("[TEST DEBUG] Waiting to receive step 3...")
            step3 = json.loads(websocket.receive_text())
            print(f"[TEST DEBUG] Received step 3: {step3}")
            
            self.assertEqual(step3["type"], "system")
            self.assertIn("history cleared", step3["message"])
            api.memory_service.clear.assert_called_once()
            print("[TEST DEBUG] Finished test_websocket_chat_message")

    def test_websocket_chat_interruption(self):
        """Verifies WebSocket interruption client signal propagates to EventBus."""
        mock_interrupt_listener = MagicMock()
        mock_interrupt_listener.__name__ = "mock_interrupt_listener"
        api.event_bus.subscribe("interrupt", mock_interrupt_listener)
        
        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_text(json.dumps({"type": "interrupt"}))
            
            # Wait briefly to let event process in event loop
            import time
            time.sleep(0.05)
            
            mock_interrupt_listener.assert_called_once()
            
        # Clean up listener subscription
        api.event_bus.unsubscribe("interrupt", mock_interrupt_listener)

def run_all() -> bool:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestApiEndpoints)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
