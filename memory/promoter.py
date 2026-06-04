import time
from datetime import datetime
from typing import Any, List, Dict
from memory.vault import ObsidianVault
from memory.scorer import ImportanceScorer
from memory.extractor import MemoryExtractor
from memory.linker import ObsidianLinker
from memory.models import CandidateMemory

class MemoryPromoter:
    """Orchestrates the Memory Promotion Pipeline:
    Conversation -> Memory Extraction -> Candidate Memories -> Importance Scoring -> Routing -> Vault Update
    """
    
    def __init__(
        self,
        vault: ObsidianVault,
        scorer: ImportanceScorer,
        extractor: MemoryExtractor,
        linker: ObsidianLinker,
        llm_service: Any
    ):
        self.vault = vault
        self.scorer = scorer
        self.extractor = extractor
        self.linker = linker
        self.llm_service = llm_service
        
    def promote_conversation_turn(self, user_msg: str, assistant_msg: str):
        """Processes a single user-assistant exchange, running extraction and updating the vault."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # 1. Extract candidates
        candidates = self.extractor.extract_memories(user_msg, assistant_msg)
        if not candidates:
            # Even if no memories, let's log the conversation exchange to Daily Note
            self._log_conversation_to_daily(date_str, user_msg, assistant_msg)
            return
            
        # Log conversation first
        self._log_conversation_to_daily(date_str, user_msg, assistant_msg)
        
        vault_notes = self.vault.list_all_notes()
        
        # 2. Process each candidate memory
        for memory in candidates:
            score, routing = self.scorer.score_and_route(memory)
            
            if routing == "discard":
                continue
                
            # Run auto-linker on the fact text
            linked_fact = self.linker.auto_link_text(memory.fact, vault_notes)
            
            if routing == "daily_only":
                self._log_memory_to_daily(date_str, f"- [Daily Only] {linked_fact} (Score: {score:.2f})")
            elif routing == "promote":
                # Promoted to long-term memory
                category = memory.category
                entity_name = memory.entity_name
                
                # Update/Create note
                self._update_or_create_long_term_note(category, entity_name, memory.fact, score)
                
                # Log promotion link to daily note
                self._log_memory_to_daily(
                    date_str, 
                    f"- [Promoted] {linked_fact} (Score: {score:.2f}) -> [[{entity_name}]]"
                )
                
                # Update backlinks (source is Daily Note, target is Promoted Note)
                self.linker.update_backlinks("Daily", date_str, category, entity_name, self.vault)
                
    def _log_conversation_to_daily(self, date_str: str, user_msg: str, assistant_msg: str):
        """Appends user-assistant dialogue turn under ## Conversations section of Daily note."""
        convo_line = f"- User: {user_msg}\n- Jarvis: {assistant_msg}\n"
        self.vault.append_to_daily_section(date_str, "Conversations", convo_line)
        
    def _log_memory_to_daily(self, date_str: str, log_line: str):
        """Appends extracted memory log under ## Extracted Memories section of Daily note."""
        self.vault.append_to_daily_section(date_str, "Extracted Memories", log_line)
        
    def _update_or_create_long_term_note(self, category: str, entity_name: str, new_fact: str, score: float):
        """Updates or creates a long-term category note, invoking the LLM for conflict handling and merging."""
        metadata = {}
        body = ""
        is_new = True
        
        if self.vault.note_exists(category, entity_name):
            metadata, body = self.vault.read_note(category, entity_name)
            is_new = False
            
        # Update metadata decay/confidence entries
        metadata["last_accessed"] = time.time()
        metadata["importance"] = max(metadata.get("importance", 0.0), score)
        metadata["times_retrieved"] = metadata.get("times_retrieved", 0)
        
        if is_new:
            metadata["created_at"] = time.time()
            metadata["confidence"] = 0.90
            metadata["source"] = "conversation"
            metadata["last_verified"] = time.time()
            metadata["aliases"] = []
            
            # Simple auto-link of the initial fact
            vault_notes = self.vault.list_all_notes()
            linked_fact = self.linker.auto_link_text(new_fact, vault_notes, current_title=entity_name)
            
            body = (
                f"# {entity_name}\n\n"
                f"## Facts & Details\n"
                f"- {linked_fact} (Extracted: {datetime.now().strftime('%Y-%m-%d')})\n"
            )
            self.vault.write_note(category, entity_name, metadata, body)
        else:
            # Query LLM to merge and check for conflicts
            updated_body = self._run_llm_note_merge(entity_name, body, new_fact)
            self.vault.write_note(category, entity_name, metadata, updated_body)
            
    def _run_llm_note_merge(self, entity_name: str, existing_body: str, new_fact: str) -> str:
        """Invokes LLM generate_json to merge a new fact into an existing note body, handling conflicts."""
        system_prompt = (
            f"You are the Vault Note Merger for the JarvBoi assistant.\n"
            f"Your job is to merge a new fact into the existing markdown body for note '{entity_name}'.\n\n"
            f"GUIDELINES:\n"
            f"1. Do not duplicate facts already present in the note.\n"
            f"2. Add the new fact to the appropriate bulleted list or create one under '## Facts & Details'.\n"
            f"3. CONFLICT HANDLING: If the new fact directly contradicts existing facts in the note (e.g. 'Fav color = red' vs 'Fav color = blue'), do NOT overwrite the older fact. Instead, create or append to a '## Conflicting Information' section at the bottom. Format conflicts as:\n"
            f"   - Old Fact (older)\n"
            f"   - New Fact (newer)\n"
            f"   Status: unresolved\n"
            f"4. Output valid, clean Markdown for the updated body.\n\n"
            f"You MUST respond ONLY with a JSON object containing a single key 'updated_body':\n"
            f"{{\n"
            f"  \"updated_body\": \"the full updated markdown note content\"\n"
            f"}}"
        )
        
        user_content = (
            f"Existing Note Body:\n\"\"\"\n{existing_body}\n\"\"\"\n\n"
            f"New Fact to Add:\n\"{new_fact}\""
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        schema = {
            "type": "OBJECT",
            "properties": {
                "updated_body": {"type": "STRING"}
            },
            "required": ["updated_body"]
        }
        
        try:
            res = self.llm_service.generate_json(messages, response_schema=schema)
            return res.get("updated_body", existing_body)
        except Exception:
            # Fallback: simple append
            return existing_body.strip() + f"\n- {new_fact} (Extracted: {datetime.now().strftime('%Y-%m-%d')})\n"
