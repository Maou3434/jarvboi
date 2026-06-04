import time
import math
import re
from typing import List, Dict, Any, Set, Optional
from memory.vault import ObsidianVault
from memory.indexer import ObsidianIndexer
from memory.graph import ObsidianGraph

class ObsidianRetriever:
    """Retrieves and ranks relevant memories combining semantic search, 
    graph expansion, recency, and importance scoring.
    """
    
    def __init__(
        self,
        vault: ObsidianVault,
        indexer: ObsidianIndexer,
        graph: ObsidianGraph,
        w_semantic: float = 0.50,
        w_graph: float = 0.20,
        w_recency: float = 0.15,
        w_importance: float = 0.15
    ):
        self.vault = vault
        self.indexer = indexer
        self.graph = graph
        self.w_semantic = w_semantic
        self.w_graph = w_graph
        self.w_recency = w_recency
        self.w_importance = w_importance
        
    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Finds primary notes via semantic search, expands to 1-hop linked notes,
        ranks the candidates, and returns the sorted records.
        """
        # Dynamic import to avoid circular dependencies
        from services.memory_service import EmbeddingClient
        from services.memory_service import cosine_similarity
        
        query_embedding = EmbeddingClient.get_embedding(query)
        if not query_embedding:
            return []
            
        # 1. Vector Search for primary hits
        primary_hits = self.indexer.search(query_embedding, top_k=top_k)
        if not primary_hits:
            return []
            
        # Compile unique candidate set
        candidates: Dict[str, Dict[str, Any]] = {}
        for hit in primary_hits:
            title = hit["title"]
            candidates[title] = {
                "title": title,
                "category": hit["category"],
                "body": hit["body"],
                "path": hit["path"],
                "semantic_score": hit["score"],
                "graph_hop": 0
            }
            
        # 2. Graph Expansion (1-hop linked notes)
        linked_expanded: Set[str] = set()
        for title in list(candidates.keys()):
            linked_titles = self.graph.get_connected_notes(title)
            for linked in linked_titles:
                if linked not in candidates and linked not in linked_expanded:
                    # Try to locate the note in the vault
                    found_note = self._find_note_in_vault(linked)
                    if found_note:
                        linked_expanded.add(linked)
                        candidates[linked] = {
                            "title": linked,
                            "category": found_note["category"],
                            "body": found_note["body"],
                            "path": found_note["rel_path"],
                            "semantic_score": None, # will be calculated or estimated
                            "graph_hop": 1
                        }
                        
        # 3. Rank Candidates with combined score
        ranked_list = []
        current_time = time.time()
        
        for title, info in candidates.items():
            # Check cached note files to read updated mtime and metadata
            note_meta, note_body = self.vault.read_note(info["category"], title)
            
            # Semantic similarity score
            sem_score = info["semantic_score"]
            if sem_score is None:
                # Calculate embedding similarity for linked note directly from text
                text_to_embed = f"Title: {title}\nCategory: {info['category']}\nContent:\n{note_body}"
                linked_emb = EmbeddingClient.get_embedding(text_to_embed)
                if linked_emb:
                    sem_score = cosine_similarity(query_embedding, linked_emb)
                else:
                    sem_score = 0.30 # Default low estimate if embedding fails
            
            # Graph proximity score
            graph_prox = 1.0 if info["graph_hop"] == 0 else 0.5
            
            # Recency score (decay based on last modified time)
            mtime = note_meta.get("last_accessed", note_meta.get("created_at", current_time))
            age_days = (current_time - mtime) / 86400.0
            recency_score = 1.0 / (1.0 + max(0.0, age_days))
            
            # Importance score from note metadata
            importance_score = note_meta.get("importance", 0.0)
            
            # Combined score calculation
            combined_score = (
                self.w_semantic * sem_score +
                self.w_graph * graph_prox +
                self.w_recency * recency_score +
                self.w_importance * importance_score
            )
            
            ranked_list.append({
                "title": title,
                "category": info["category"],
                "body": note_body,
                "metadata": note_meta,
                "combined_score": combined_score,
                "semantic_score": sem_score
            })
            
            # Reinforce: update last accessed time and times_retrieved count in note frontmatter
            note_meta["last_accessed"] = current_time
            note_meta["times_retrieved"] = note_meta.get("times_retrieved", 0) + 1
            self.vault.write_note(info["category"], title, note_meta, note_body)
            
        # Sort by combined score descending
        ranked_list.sort(key=lambda x: x["combined_score"], reverse=True)
        return ranked_list
        
    def build_context(self, query: str, ranked_notes: List[Dict[str, Any]]) -> str:
        """Compresses long note bodies, extracts matching headers, and outputs the packaged context."""
        context_parts = []
        
        for note in ranked_notes:
            title = note["title"]
            category = note["category"]
            body = note["body"]
            score = note["combined_score"]
            
            # Extract relevant parts to keep token usage low
            relevant_section = self._extract_relevant_sections(body, query)
            
            context_parts.append(
                f"--- NOTE: {category}/{title}.md (Retrieval Match Score: {score:.2f}) ---\n"
                f"{relevant_section.strip()}\n"
            )
            
        return "\n".join(context_parts)
        
    def _find_note_in_vault(self, title: str) -> Optional[Dict[str, Any]]:
        """Scans all vault categories to find a note matching the title."""
        for cat in self.vault.categories:
            if self.vault.note_exists(cat, title):
                path = self.vault.get_note_path(cat, title)
                rel_path = f"{cat}/{title}.md"
                return {"category": cat, "rel_path": rel_path}
        return None
        
    def _extract_relevant_sections(self, body: str, query: str) -> str:
        """Splits body by markdown headers and matches query words to filter irrelevant sections."""
        words = set(w.lower() for w in re.sub(r'[^\w\s]', '', query).split() if len(w) > 3)
        if not words or len(body.split()) < 150:
            return body
            
        # Split note into sections by headers
        sections = re.split(r'(?=\n#+ )', "\n" + body)
        selected = []
        
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
                
            # If it's the title header or contains matching query words, select it
            sec_lower = sec.lower()
            if sec.startswith("# ") or any(word in sec_lower for word in words):
                selected.append(sec)
                
        if not selected:
            return body[:500] + "\n... [truncated for token conservation] ..."
            
        return "\n\n".join(selected)
