import os
import time
import shutil
from datetime import datetime
from typing import Any, List, Dict
from memory.vault import ObsidianVault
from memory.indexer import ObsidianIndexer
from memory.graph import ObsidianGraph

class MemoryReflector:
    """Performs periodic reflection: memory decay/aging, duplicate consolidation,
    high-level insight synthesis, stale note archiving, and index/graph refreshing.
    """
    
    def __init__(
        self,
        vault: ObsidianVault,
        indexer: ObsidianIndexer,
        graph: ObsidianGraph,
        llm_service: Any,
        decay_rate: float = 0.05, # decay of importance per day
        archive_threshold: float = 0.20
    ):
        self.vault = vault
        self.indexer = indexer
        self.graph = graph
        self.llm_service = llm_service
        self.decay_rate = decay_rate
        self.archive_threshold = archive_threshold
        
    def run_reflection(self):
        """Main entry point for running a full reflection sequence."""
        current_time = time.time()
        
        # 1. Memory Decay & Archiving
        self._apply_decay_and_archive(current_time)
        
        # 2. LLM Consolidated Synthesis (Summarizing daily logs)
        self._consolidate_daily_summaries()
        
        # 3. Refresh Graph and Index
        self.graph.rebuild_graph(self.vault)
        self.indexer.rebuild_index(self.vault)
        
    def _apply_decay_and_archive(self, current_time: float):
        """Scans notes, reduces importance based on last accessed time, and moves stale items to Archive."""
        notes = self.vault.list_all_notes()
        
        for note in notes:
            category = note["category"]
            title = note["title"]
            
            # Skip Daily and Archive notes from decay process
            if category in ("Daily", "Archive"):
                continue
                
            metadata = note["metadata"]
            body = note["body"]
            
            last_accessed = metadata.get("last_accessed", metadata.get("created_at", current_time))
            times_retrieved = metadata.get("times_retrieved", 0)
            importance = metadata.get("importance", 0.5)
            
            elapsed_days = (current_time - last_accessed) / 86400.0
            
            # Unused memories decay; frequently used ones are reinforced (reduce decay penalty)
            decay_penalty = self.decay_rate * elapsed_days
            if times_retrieved > 5:
                decay_penalty *= 0.2 # slower decay
                
            new_importance = max(0.0, importance - decay_penalty)
            metadata["importance"] = new_importance
            
            # If importance falls below threshold, archive it
            if new_importance < self.archive_threshold:
                # Move physical file to Archive
                old_path = self.vault.get_note_path(category, title)
                new_path = self.vault.get_note_path("Archive", title)
                
                # Check if already exists in Archive
                if os.path.exists(new_path):
                    # Append index to title to prevent overwrite
                    title = f"{title}_{int(current_time)}"
                    new_path = self.vault.get_note_path("Archive", title)
                    
                # Update category in metadata
                metadata["category"] = "Archive"
                metadata["archived_at"] = current_time
                
                # Write to Archive folder and delete from old folder
                self.vault.write_note("Archive", title, metadata, body)
                if os.path.exists(old_path):
                    os.remove(old_path)
                    
                # Log archiving to today's Daily note
                date_str = datetime.now().strftime("%Y-%m-%d")
                self._log_archived_memory(date_str, f"- [Archived] Note '{title}' from {category} due to low importance ({new_importance:.2f}).")
            else:
                # Write back note with updated importance
                self.vault.write_note(category, title, metadata, body)
                
    def _consolidate_daily_summaries(self):
        """Analyzes recent daily logs, detects patterns, and inserts consolidated insights back into vault."""
        daily_notes = [n for n in self.vault.list_all_notes() if n["category"] == "Daily"]
        if not daily_notes:
            return
            
        # Compile content of recent daily logs (last 5 daily notes for context size)
        daily_notes = sorted(daily_notes, key=lambda x: x["title"], reverse=True)[:5]
        logs_context = ""
        for note in daily_notes:
            logs_context += f"--- DAILY LOG {note['title']} ---\n{note['body']}\n\n"
            
        system_prompt = (
            "You are the Memory Reflection consolidation agent for the JarvBoi assistant.\n"
            "Your job is to analyze the recent daily log summaries and synthesize them into high-level knowledge summaries.\n"
            "Identify recurring projects progress, user preferences, and general facts.\n"
            "Consolidate multiple minor updates into high-level updates for permanent notes.\n\n"
            "You MUST respond ONLY with a JSON object conforming to this schema:\n"
            "{\n"
            "  \"insights\": [\n"
            "    {\n"
            "      \"entity_name\": \"name of the project/person/concept to update (e.g. 'Jarvis', 'Abi')\",\n"
            "      \"category\": \"People|Projects|Concepts|Procedures\",\n"
            "      \"summary\": \"High-level consolidated summary or milestone fact (e.g. 'Successfully built the core long-term memory system v2')\",\n"
            "      \"importance\": float\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here are the recent logs:\n{logs_context}"}
        ]
        
        schema = {
            "type": "OBJECT",
            "properties": {
                "insights": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "entity_name": {"type": "STRING"},
                            "category": {"type": "STRING", "enum": ["People", "Projects", "Concepts", "Procedures"]},
                            "summary": {"type": "STRING"},
                            "importance": {"type": "NUMBER"}
                        },
                        "required": ["entity_name", "category", "summary", "importance"]
                    }
                }
            },
            "required": ["insights"]
        }
        
        try:
            res = self.llm_service.generate_json(messages, response_schema=schema)
            insights = res.get("insights", [])
            
            # Process insights by promoting them
            for ins in insights:
                entity = ins.get("entity_name")
                cat = ins.get("category")
                summary = ins.get("summary")
                importance = float(ins.get("importance", 0.8))
                
                # Check target file and append/merge
                metadata = {}
                body = ""
                is_new = True
                
                if self.vault.note_exists(cat, entity):
                    metadata, body = self.vault.read_note(cat, entity)
                    is_new = False
                    
                metadata["last_accessed"] = time.time()
                metadata["importance"] = max(metadata.get("importance", 0.0), importance)
                metadata["times_retrieved"] = metadata.get("times_retrieved", 0)
                
                if is_new:
                    metadata["created_at"] = time.time()
                    metadata["confidence"] = 0.90
                    metadata["source"] = "reflection"
                    metadata["last_verified"] = time.time()
                    metadata["aliases"] = []
                    body = f"# {entity}\n\n## Facts & Details\n- {summary} (Synthesized: {datetime.now().strftime('%Y-%m-%d')})\n"
                    self.vault.write_note(cat, entity, metadata, body)
                else:
                    # Append synthesis to facts section
                    if "## Facts & Details" in body:
                        parts = body.split("## Facts & Details", 1)
                        rest = parts[1].strip()
                        new_body = parts[0] + "## Facts & Details\n- " + summary + f" (Synthesized: {datetime.now().strftime('%Y-%m-%d')})\n"
                        if rest:
                            new_body += rest
                        body = new_body
                    else:
                        body = body.strip() + f"\n\n## Facts & Details\n- {summary} (Synthesized: {datetime.now().strftime('%Y-%m-%d')})\n"
                    self.vault.write_note(cat, entity, metadata, body)
        except Exception:
            pass
            
    def _log_archived_memory(self, date_str: str, log_line: str):
        """Appends archive information in daily notes."""
        self.vault.append_to_daily_section(date_str, "Extracted Memories", log_line)
