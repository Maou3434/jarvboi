import logging
import sys
from config.settings import Settings

# Ensure standard output streams on Windows gracefully handle emojis/non-ASCII without crashing
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(errors='replace')
    except Exception:
        pass

def setup_logger() -> logging.Logger:
    """Configures and returns the application logger."""
    logger = logging.getLogger(Settings.SYSTEM_NAME)
    
    # If logger is already configured, don't add duplicate handlers
    if logger.handlers:
        return logger
        
    logger.setLevel(getattr(logging, Settings.LOG_LEVEL.upper(), logging.INFO))
    
    # Create file handler with absolute path relative to project root
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_file_path = Settings.LOG_FILE if os.path.isabs(Settings.LOG_FILE) else os.path.join(project_root, Settings.LOG_FILE)
    
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        "[%(levelname)s] %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Create a default logger instance
logger = setup_logger()
