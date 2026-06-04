import re

# Stop words filter to clean sentences before similarity calculations
NOISY_WORDS = {
    "what", "was", "that", "is", "the", "a", "an", "and", "user", "jarvis", 
    "to", "of", "in", "it", "for", "on", "with", "as", "at", "by", "this", 
    "there", "they", "we", "you", "i", "me", "my", "your", "he", "she"
}

def clean_text_for_similarity(text: str) -> str:
    """Standardizes text by converting to lowercase and stripping punctuation/symbols."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return text

def jaccard_similarity(text1: str, text2: str) -> float:
    """Calculates word-overlap (Jaccard) similarity for fallback keyword search, filtering noisy words."""
    clean1 = clean_text_for_similarity(text1)
    clean2 = clean_text_for_similarity(text2)
    
    words1 = set(w for w in clean1.split() if w not in NOISY_WORDS)
    words2 = set(w for w in clean2.split() if w not in NOISY_WORDS)
    
    # Fallback to unfiltered lists if all words are considered noisy
    if not words1:
        words1 = set(clean1.split())
    if not words2:
        words2 = set(clean2.split())
        
    if not words1 or not words2:
        return 0.0
    return len(words1.intersection(words2)) / len(words1.union(words2))
