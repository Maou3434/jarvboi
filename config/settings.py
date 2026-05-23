import os

class Settings:
    """System-wide configuration settings for Jarvboi."""
    
    # Ollama configurations
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "mistral")
    
    # LLM generation parameters
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))  # Default to 0.0 for deterministic tool calling
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "jarvboi.log")
    
    # System settings
    SYSTEM_NAME: str = "Jarvboi"
    
    # Browser automation configurations
    BROWSER_HEADLESS: bool = os.getenv("BROWSER_HEADLESS", "False").lower() in ("true", "1", "yes")
    BROWSER_TIMEOUT: int = int(os.getenv("BROWSER_TIMEOUT", "15000"))
    BROWSER_CONNECT_CDP: bool = os.getenv("BROWSER_CONNECT_CDP", "False").lower() in ("true", "1", "yes")
    BROWSER_CDP_URL: str = os.getenv("BROWSER_CDP_URL", "http://127.0.0.1:9222")
