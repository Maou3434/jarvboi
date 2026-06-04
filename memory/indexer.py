import os
import json
import uuid
import time
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from memory.vault import ObsidianVault

class ObsidianIndexer:
    """Uses a local, serverless Qdrant database to index notes in the Obsidian Vault.
    Rebuilds the index incrementally by checking file modification times.
    """
    
    def __init__(self, db_path: Optional[str] = None, collection_name: str = "obsidian_notes"):
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, "scratch", "qdrant_db")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
        self.client = QdrantClient(path=db_path)
        self.collection_name = collection_name
        self.meta_cache_path = os.path.join(os.path.dirname(db_path), "obsidian_indexer_meta.json")
        self.meta_cache: Dict[str, float] = self._load_meta_cache()
        self.is_initialized = False
        
    def _load_meta_cache(self) -> Dict[str, float]:
        if os.path.exists(self.meta_cache_path):
            try:
                with open(self.meta_cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
        
    def _save_meta_cache(self):
        try:
            with open(self.meta_cache_path, "w", encoding="utf-8") as f:
                json.dump(self.meta_cache, f, indent=2)
        except Exception:
            pass
            
    def _ensure_collection(self, vector_size: int):
        if self.is_initialized:
            return
            
        # Check if collection exists
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        
        if not exists:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )
        self.is_initialized = True
        
    def rebuild_index(self, vault: ObsidianVault):
        """Scans the vault, indexing new or modified notes, and deleting removed ones."""
        # Dynamic import to avoid circular dependency
        from services.memory_service import EmbeddingClient
        
        notes = vault.list_all_notes()
        if not notes:
            return
            
        # Get dynamic dimension size
        dummy = EmbeddingClient.get_embedding("test")
        vector_size = len(dummy) if dummy else 768
        self._ensure_collection(vector_size)
        
        active_paths = set()
        points_to_upsert = []
        updated_cache = {}
        
        for note in notes:
            rel_path = note["rel_path"]
            active_paths.add(rel_path)
            mtime = note["mtime"]
            
            # Check if cache is up-to-date
            if rel_path in self.meta_cache and self.meta_cache[rel_path] == mtime:
                updated_cache[rel_path] = mtime
                continue
                
            # Content to embed (Note Title + Content)
            text_to_embed = f"Title: {note['title']}\nCategory: {note['category']}\nContent:\n{note['body']}"
            embedding = EmbeddingClient.get_embedding(text_to_embed)
            if not embedding:
                continue
                
            # Create deterministic UUID from relative path
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, rel_path))
            
            points_to_upsert.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "path": rel_path,
                    "title": note["title"],
                    "category": note["category"],
                    "body": note["body"],
                    "updated_at": mtime
                }
            ))
            updated_cache[rel_path] = mtime
            
        # 1. Upsert points in batches
        if points_to_upsert:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points_to_upsert
            )
            
        # 2. Find and delete removed notes
        removed_paths = set(self.meta_cache.keys()) - active_paths
        for removed in removed_paths:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, removed))
            try:
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=[point_id]
                )
            except Exception:
                pass
                
        # 3. Update cache
        self.meta_cache = updated_cache
        self._save_meta_cache()
        
    def search(self, query_embedding: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
        """Searches the indexed notes using vector similarity."""
        if not self.is_initialized:
            # Check collection status
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                return []
            self.is_initialized = True
            
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=top_k
        )
        
        output = []
        for hit in results.points:
            output.append({
                "path": hit.payload.get("path"),
                "title": hit.payload.get("title"),
                "category": hit.payload.get("category"),
                "body": hit.payload.get("body"),
                "score": hit.score
            })
        return output
        
    def delete_all(self):
        """Clears/disposes the collection."""
        try:
            self.client.delete_collection(self.collection_name)
            self.is_initialized = False
            if os.path.exists(self.meta_cache_path):
                os.remove(self.meta_cache_path)
            self.meta_cache = {}
        except Exception:
            pass

    def close(self):
        """Closes the client connections and releases locks."""
        try:
            self.client.close()
        except Exception:
            pass
