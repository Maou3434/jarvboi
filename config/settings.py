import os

def load_env():
    """Manually parse .env file to support loading environment variables without python-dotenv."""
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        # Strip spaces and surrounding quotes
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")
        except Exception:
            pass

# Load environment variables from .env file immediately
load_env()

class Settings:
    """System-wide configuration settings for Jarvboi."""
    
    # Provider configuration (defaults to 'gemini', can be 'ollama')
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    
    # Gemini API configurations
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
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
    
    # Speech-to-Text configurations
    STT_BACKEND: str = os.getenv("STT_BACKEND", "whisper")  # 'whisper' or 'google'
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "tiny.en")  # e.g. tiny.en, base.en, tiny, base
    
    # Browser automation configurations
    BROWSER_HEADLESS: bool = os.getenv("BROWSER_HEADLESS", "False").lower() in ("true", "1", "yes")
    BROWSER_TIMEOUT: int = int(os.getenv("BROWSER_TIMEOUT", "15000"))
    BROWSER_CONNECT_CDP: bool = os.getenv("BROWSER_CONNECT_CDP", "False").lower() in ("true", "1", "yes")
    BROWSER_CDP_URL: str = os.getenv("BROWSER_CDP_URL", "http://127.0.0.1:9222")
