from typing import Dict, Any, Tuple
from memory.models import CandidateMemory

class ImportanceScorer:
    """Computes the importance score of a candidate memory and decides on promotion level."""
    
    def __init__(
        self,
        weight_relevance: float = 0.35,
        weight_recurrence: float = 0.25,
        weight_novelty: float = 0.20,
        weight_user_signal: float = 0.20,
        threshold_discard: float = 0.30,
        threshold_promote: float = 0.70
    ):
        self.w_relevance = weight_relevance
        self.w_recurrence = weight_recurrence
        self.w_novelty = weight_novelty
        self.w_user_signal = weight_user_signal
        
        self.t_discard = threshold_discard
        self.t_promote = threshold_promote
        
    def calculate_score(self, memory: CandidateMemory) -> float:
        """Calculates memory importance score using formula:
        score = 0.35 * relevance + 0.25 * recurrence + 0.20 * novelty + 0.20 * user_signal
        """
        score = (
            self.w_relevance * memory.relevance +
            self.w_recurrence * memory.recurrence +
            self.w_novelty * memory.novelty +
            self.w_user_signal * memory.user_signal
        )
        # Clamp between 0.0 and 1.0
        return max(0.0, min(1.0, score))
        
    def get_routing(self, score: float) -> str:
        """Decides memory storage path based on computed score.
        Returns 'discard', 'daily_only', or 'promote'.
        """
        if score < self.t_discard:
            return "discard"
        elif score <= self.t_promote:
            return "daily_only"
        else:
            return "promote"
            
    def score_and_route(self, memory: CandidateMemory) -> Tuple[float, str]:
        """Calculates score and routing in one pass."""
        score = self.calculate_score(memory)
        routing = self.get_routing(score)
        return score, routing
