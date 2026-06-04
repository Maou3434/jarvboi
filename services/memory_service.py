import os
import json
import math
import time
import queue
import threading
import urllib.request
from typing import List, Dict, Any, Optional
from config.settings import Settings
from utils.logger import logger

# --- Inline Math Utility Functions ---
def dot_product(v1: List[float], v2: List[float]) -> float:
    return sum(x * y for x, y in zip(v1, v2))

def magnitude(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    mag1 = magnitude(v1)
    mag2 = magnitude(v2)
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot_product(v1, v2) / (mag1 * mag2)

from utils.text_helpers import NOISY_WORDS, clean_text_for_similarity, jaccard_similarity


# --- Embedding Retrieval Client ---
class EmbeddingClient:
    """Handles generating embeddings from Gemini or Ollama depending on configuration."""
    
    @staticmethod
    def get_embedding(text: str) -> Optional[List[float]]:
        provider = Settings.LLM_PROVIDER
        if provider == "gemini":
            return EmbeddingClient._get_gemini_embedding(text)
        elif provider == "ollama":
            return EmbeddingClient._get_ollama_embedding(text)
        return None

    @staticmethod
    def _get_gemini_embedding(text: str) -> Optional[List[float]]:
        api_key = Settings.GEMINI_API_KEY
        if not api_key:
            return None
            
        model = "text-embedding-004"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={api_key}"
        payload = {
            "model": f"models/{model}",
            "content": {
                "parts": [{"text": text}]
            }
        }
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload).encode("utf-8")
        
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5.0) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                return res_json.get("embedding", {}).get("values")
        except Exception as e:
            logger.error(f"[EmbeddingClient] Failed to fetch Gemini embedding: {e}")
            return None

    @staticmethod
    def _get_ollama_embedding(text: str) -> Optional[List[float]]:
        try:
            with urllib.request.urlopen(Settings.OLLAMA_HOST, timeout=1.0) as conn:
                pass
        except Exception:
            return None

        import ollama
        models_to_try = ["nomic-embed-text", Settings.OLLAMA_MODEL]
        
        for model in models_to_try:
            try:
                res = ollama.embeddings(model=model, prompt=text)
                if "embedding" in res:
                    return res["embedding"]
            except Exception:
                try:
                    res = ollama.embed(model=model, input=text)
                    if "embeddings" in res and res["embeddings"]:
                        return res["embeddings"][0]
                except Exception:
                    continue
        return None


# --- Conversational sliding-window memory ---
class ConversationMemory:
    """Manages the in-memory sliding window chat history."""
    
    def __init__(self, max_messages: int = 40):
        self.messages: List[Dict[str, str]] = []
        self.max_messages = max_messages
        
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self._trim_memory()
        
    def add_tool_result(self, tool_name: str, result: str):
        self.messages.append({
            "role": "system",
            "content": f"TOOL EXECUTION RESULT [{tool_name}]:\n{result}"
        })
        self._trim_memory()
        
    def get_history(self) -> List[Dict[str, str]]:
        return self.messages
        
    def clear(self):
        system_messages = [msg for msg in self.messages if msg["role"] == "system" and "TOOL EXECUTION" not in msg["content"]]
        self.messages = system_messages
        
    def _trim_memory(self):
        if len(self.messages) > self.max_messages:
            has_system = len(self.messages) > 0 and self.messages[0]["role"] == "system"
            if has_system:
                sys_msg = self.messages[0]
                self.messages = [sys_msg] + self.messages[-(self.max_messages - 1):]
            else:
                self.messages = self.messages[-self.max_messages:]





# --- Consolidated Memory Service ---
from memory import (
    ObsidianVault,
    ImportanceScorer,
    MemoryExtractor,
    ObsidianLinker,
    MemoryPromoter,
    ObsidianIndexer,
    ObsidianGraph,
    ObsidianRetriever,
    MemoryReflector
)

class MemoryService:
    """Consolidated memory service managing short-term conversation logs (Working Memory)
    and long-term Obsidian-based memory (Episodic, Semantic, Procedural).
    """
    
    def __init__(self, event_bus=None, filepath: Optional[str] = None, db_service=None):
        self.event_bus = event_bus
        self.conversation_memory = ConversationMemory(max_messages=50)
        
        # Initialize LLM & DB service dependencies
        from services.llm_service import LLMService
        from services.db_service import DbService
        self.llm_service = LLMService()
        self.db_service = db_service or DbService()
        
        # Initialize Obsidian V2 Memory System Components
        self.vault = ObsidianVault()
        self.scorer = ImportanceScorer()
        self.extractor = MemoryExtractor(self.llm_service)
        self.linker = ObsidianLinker()
        self.promoter = MemoryPromoter(
            vault=self.vault,
            scorer=self.scorer,
            extractor=self.extractor,
            linker=self.linker,
            llm_service=self.llm_service
        )
        self.indexer = ObsidianIndexer()
        self.graph = ObsidianGraph()
        self.retriever = ObsidianRetriever(
            vault=self.vault,
            indexer=self.indexer,
            graph=self.graph
        )
        self.reflector = MemoryReflector(
            vault=self.vault,
            indexer=self.indexer,
            graph=self.graph,
            llm_service=self.llm_service
        )
        
        # Rebuild graph and vector index upon startup
        try:
            logger.info("[MemoryService] Syncing graph and index with Obsidian Vault...")
            self.graph.rebuild_graph(self.vault)
            self.indexer.rebuild_index(self.vault)
        except Exception as e:
            logger.error(f"[MemoryService] Failed to rebuild index/graph on startup: {e}")
            
        self.queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        # Background periodic reflection thread
        self.reflection_thread = threading.Thread(target=self._reflection_loop, daemon=True)
        self.reflection_thread.start()
        
        if self.event_bus:
            self.event_bus.subscribe("save_memory", self._on_save_memory_event)
            logger.info("[MemoryService] Subscribed to 'save_memory' events on EventBus.")
            
    def _worker_loop(self):
        logger.info("[MemoryService] Worker loop thread started.")
        while True:
            try:
                logger.debug("[MemoryService] Waiting for item in queue...")
                item = self.queue.get()
                logger.debug(f"[MemoryService] Worker thread pulled item: {item}")
                if item is None:
                    break
                user_msg, assistant_msg = item
                
                # Run the V2 memory extraction & promotion pipeline
                self.promoter.promote_conversation_turn(user_msg, assistant_msg)
                
                # Rebuild index and graph to include the newly promoted items
                self.graph.rebuild_graph(self.vault)
                self.indexer.rebuild_index(self.vault)
                
                self.queue.task_done()
                logger.debug("[MemoryService] Task marked as done.")
            except Exception as e:
                logger.error(f"[MemoryService] Worker error: {e}")
                
    def _reflection_loop(self):
        # Run reflection periodically (default every 6 hours)
        # Wait 30 seconds after startup before running first reflection
        time.sleep(30.0)
        while True:
            try:
                logger.info("[MemoryService] Starting background memory reflection...")
                self.reflector.run_reflection()
                logger.info("[MemoryService] Background memory reflection completed.")
            except Exception as e:
                logger.error(f"[MemoryService] Reflection loop error: {e}")
            time.sleep(6.0 * 3600.0)
            
    def run_reflection(self):
        """Manually trigger reflection process."""
        self.reflector.run_reflection()
        
    def _on_save_memory_event(self, data: Dict[str, str]):
        """Callback executing when save_memory events are emitted on the bus."""
        logger.debug(f"[MemoryService] Received save_memory event: {data}")
        user_message = data.get("user_message", "")
        response_text = data.get("response_text", "")
        if user_message and response_text:
            self.save_memory_async(user_message, response_text)
            
    def save_memory_async(self, user_msg: str, assistant_msg: str):
        """Pushes user-assistant exchange into background processing queue."""
        logger.debug(f"[MemoryService] Putting item in queue: ({user_msg}, {assistant_msg})")
        self.queue.put((user_msg, assistant_msg))
        
    def add_short_term_message(self, role: str, content: str):
        self.conversation_memory.add_message(role, content)
        
    def add_short_term_tool_result(self, tool_name: str, result: str):
        self.conversation_memory.add_tool_result(tool_name, result)
        
    def get_short_term_history(self) -> List[Dict[str, str]]:
        return self.conversation_memory.get_history()
        
    def retrieve_long_term_context(self, query: str, top_k: int = 3) -> List[str]:
        try:
            ranked = self.retriever.retrieve(query, top_k=top_k)
            if not ranked:
                return []
            context = self.retriever.build_context(query, ranked)
            return [context]
        except Exception as e:
            logger.error(f"[MemoryService] Error in retrieve_long_term_context: {e}")
            return []
            
    def clear(self):
        """Clears short-term memory."""
        self.conversation_memory.clear()
        
    def stop(self):
        """Stops the worker thread."""
        self.queue.put(None)
        self.worker_thread.join()

