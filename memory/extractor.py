from typing import List, Dict, Any
from memory.models import CandidateMemory

class MemoryExtractor:
    """Uses the LLM service to parse a user-assistant dialogue turn and extract candidate memories."""
    
    def __init__(self, llm_service: Any):
        self.llm_service = llm_service
        
    def extract_memories(self, user_msg: str, assistant_msg: str) -> List[CandidateMemory]:
        """Queries the LLM to extract candidate memories from a single exchange."""
        system_prompt = (
            "You are the Memory Extractor module for JarvBoi, a personal AI assistant.\n"
            "Your job is to analyze the latest user-assistant interaction and extract candidate memories.\n"
            "Do not extract trivial logs or conversation filler (e.g., 'hello', 'how are you', 'thank you').\n"
            "Focus on extracting:\n"
            "1. Episodic events: What project milestones were achieved, what tasks were done, what occurred.\n"
            "2. Semantic facts: Durable information about the user (preferences, interests, relationships) or assistant setup.\n"
            "3. Procedural workflows: Custom procedures or instructions that the user wants the assistant to remember.\n\n"
            "For each memory:\n"
            "- Categorize it under one of: 'People', 'Projects', 'Concepts', 'Procedures', 'Meetings', 'Daily'.\n"
            "- Identify the target entity name (e.g. 'Abi' for People, 'Jarvis' for Projects, 'Graph Memory' for Concepts).\n"
            "- Classify the type of memory: 'episodic', 'semantic', or 'procedural'.\n"
            "- Score the following dimensions between 0.0 and 1.0:\n"
            "  * relevance: How useful is this fact for future turns?\n"
            "  * recurrence: Is this a repeating topic or process?\n"
            "  * novelty: How new/unique is this information?\n"
            "  * user_signal: Did the user explicitly ask you to remember it, state it as a key preference, or emphasize its importance?\n\n"
            "You MUST respond ONLY with a JSON object conforming exactly to this schema:\n"
            "{\n"
            "  \"candidates\": [\n"
            "    {\n"
            "      \"fact\": \"description of the fact/event/procedure\",\n"
            "      \"category\": \"People|Projects|Concepts|Procedures|Meetings|Daily\",\n"
            "      \"entity_name\": \"name of the entity (e.g. 'Abi', 'Jarvis')\",\n"
            "      \"relevance\": float,\n"
            "      \"recurrence\": float,\n"
            "      \"novelty\": float,\n"
            "      \"user_signal\": float,\n"
            "      \"memory_type\": \"episodic|semantic|procedural\",\n"
            "      \"extra_data\": {}\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        
        user_content = f"User: {user_msg}\nJarvis: {assistant_msg}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        # Enforce responseSchema for Gemini if supported
        schema = {
            "type": "OBJECT",
            "properties": {
                "candidates": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "fact": {"type": "STRING"},
                            "category": {"type": "STRING", "enum": ["People", "Projects", "Concepts", "Procedures", "Meetings", "Daily"]},
                            "entity_name": {"type": "STRING"},
                            "relevance": {"type": "NUMBER"},
                            "recurrence": {"type": "NUMBER"},
                            "novelty": {"type": "NUMBER"},
                            "user_signal": {"type": "NUMBER"},
                            "memory_type": {"type": "STRING", "enum": ["episodic", "semantic", "procedural"]},
                            "extra_data": {"type": "OBJECT"}
                        },
                        "required": ["fact", "category", "entity_name", "relevance", "recurrence", "novelty", "user_signal", "memory_type"]
                    }
                }
            },
            "required": ["candidates"]
        }
        
        try:
            res = self.llm_service.generate_json(messages, response_schema=schema)
            candidates = res.get("candidates", [])
            
            output = []
            for c in candidates:
                output.append(CandidateMemory(
                    fact=c.get("fact", ""),
                    category=c.get("category", "Daily"),
                    entity_name=c.get("entity_name", "General"),
                    relevance=float(c.get("relevance", 0.0)),
                    recurrence=float(c.get("recurrence", 0.0)),
                    novelty=float(c.get("novelty", 0.0)),
                    user_signal=float(c.get("user_signal", 0.0)),
                    memory_type=c.get("memory_type", "semantic"),
                    extra_data=c.get("extra_data", {})
                ))
            return output
        except Exception:
            return []
