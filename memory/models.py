import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class MemoryMetadata:
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    times_retrieved: int = 0
    importance: float = 0.0
    confidence: float = 1.0
    source: str = "conversation"
    last_verified: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "times_retrieved": self.times_retrieved,
            "importance": self.importance,
            "confidence": self.confidence,
            "source": self.source,
            "last_verified": self.last_verified
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryMetadata":
        if not d:
            return cls()
        return cls(
            created_at=d.get("created_at", time.time()),
            last_accessed=d.get("last_accessed", time.time()),
            times_retrieved=d.get("times_retrieved", 0),
            importance=d.get("importance", 0.0),
            confidence=d.get("confidence", 1.0),
            source=d.get("source", "conversation"),
            last_verified=d.get("last_verified", time.time())
        )

@dataclass
class CandidateMemory:
    fact: str
    category: str  # People, Projects, Concepts, Daily, Procedures, etc.
    entity_name: str
    relevance: float = 0.0
    recurrence: float = 0.0
    novelty: float = 0.0
    user_signal: float = 0.0
    memory_type: str = "semantic"  # episodic, semantic, procedural
    extra_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class EpisodicMemory:
    summary: str
    timestamp: str
    project: Optional[str] = None
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

@dataclass
class SemanticMemory:
    subject: str
    relation: str
    object: str
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

@dataclass
class ProceduralMemory:
    task: str
    steps: List[str]
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)
