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

NOISY_WORDS = {"what", "was", "that", "is", "the", "a", "an", "and", "user", "jarvis", "to", "of", "in", "it", "for", "on", "with", "as", "at", "by", "this", "there", "they", "we", "you", "i", "me", "my", "your", "he", "she", "it"}

def clean_text_for_similarity(text: str) -> str:
    import re
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return text

def jaccard_similarity(text1: str, text2: str) -> float:
    """Calculates word-overlap (Jaccard) similarity for fallback keyword search, filtering noisy words."""
    clean1 = clean_text_for_similarity(text1)
    clean2 = clean_text_for_similarity(text2)
    
    words1 = set(w for w in clean1.split() if w not in NOISY_WORDS)
    words2 = set(w for w in clean2.split() if w not in NOISY_WORDS)
    
    if not words1:
        words1 = set(clean1.split())
    if not words2:
        words2 = set(clean2.split())
        
    if not words1 or not words2:
        return 0.0
    return len(words1.intersection(words2)) / len(words1.union(words2))


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


# --- Long-term persistent vector storage ---
class VectorStore:
    """A persistent, lightweight, file-backed vector database."""
    
    def __init__(self, filepath: Optional[str] = None):
        if filepath is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            scratch_dir = os.path.join(project_root, "scratch")
            os.makedirs(scratch_dir, exist_ok=True)
            self.filepath = os.path.join(scratch_dir, "vector_memory.json")
        else:
            self.filepath = filepath
            
        self.memories: List[Dict[str, Any]] = []
        self.load()
        
    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.memories = json.load(f)
                logger.info(f"[VectorStore] Loaded {len(self.memories)} memories.")
            except Exception as e:
                logger.error(f"[VectorStore] Failed to load memories: {e}")
                self.memories = []
        else:
            self.memories = []
            
    def save(self):
        try:
            print(f"[VectorStore PRINT] Saving memories to {self.filepath}, count: {len(self.memories)}")
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.memories, f, indent=2)
        except Exception as e:
            logger.error(f"[VectorStore] Failed to save memories: {e}")
            
    def add_memory(self, user_query: str, assistant_response: str):
        print(f"[VectorStore PRINT] add_memory started for query '{user_query}'")
        memory_text = f"User: {user_query}\nJarvis: {assistant_response}"
        embedding = EmbeddingClient.get_embedding(memory_text)
        print(f"[VectorStore PRINT] add_memory embedding generated (is None: {embedding is None})")
        
        self.memories.append({
            "text": memory_text,
            "timestamp": time.time(),
            "embedding": embedding
        })
        self.save()
        print(f"[VectorStore PRINT] add_memory finished")
        
    def retrieve_context(self, query: str, top_k: int = 3) -> List[str]:
        if not self.memories:
            return []
            
        query_embedding = EmbeddingClient.get_embedding(query)
        scored_memories = []
        
        if query_embedding is not None:
            for mem in self.memories:
                if mem.get("embedding") is not None:
                    sim = cosine_similarity(query_embedding, mem["embedding"])
                    scored_memories.append((sim, mem["text"]))
                else:
                    sim = jaccard_similarity(query, mem["text"])
                    scored_memories.append((sim * 0.7, mem["text"]))
        else:
            for mem in self.memories:
                sim = jaccard_similarity(query, mem["text"])
                scored_memories.append((sim, mem["text"]))
                
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        relevant_memories = []
        for sim, text in scored_memories:
            is_embedding_search = (query_embedding is not None)
            threshold = 0.35 if is_embedding_search else 0.05
            if sim > threshold:
                relevant_memories.append(text)
                
        return relevant_memories[:top_k]


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
        print("[MemoryService PRINT] Worker loop thread started.")
        while True:
            try:
                print("[MemoryService PRINT] Waiting for item in queue...")
                item = self.queue.get()
                print(f"[MemoryService PRINT] Worker thread pulled item: {item}")
                if item is None:
                    break
                user_msg, assistant_msg = item
                
                # Run the V2 memory extraction & promotion pipeline
                self.promoter.promote_conversation_turn(user_msg, assistant_msg)
                
                # Rebuild index and graph to include the newly promoted items
                self.graph.rebuild_graph(self.vault)
                self.indexer.rebuild_index(self.vault)
                
                self.queue.task_done()
                print("[MemoryService PRINT] Task marked as done.")
            except Exception as e:
                print(f"[MemoryService PRINT] Worker error: {e}")
                
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
        print(f"[MemoryService PRINT] Received save_memory event: {data}")
        user_message = data.get("user_message", "")
        response_text = data.get("response_text", "")
        if user_message and response_text:
            self.save_memory_async(user_message, response_text)
            
    def save_memory_async(self, user_msg: str, assistant_msg: str):
        """Pushes user-assistant exchange into background processing queue."""
        print(f"[MemoryService PRINT] Putting item in queue: ({user_msg}, {assistant_msg})")
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

