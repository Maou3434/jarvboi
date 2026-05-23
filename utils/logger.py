import logging
import sys
from config.settings import Settings

def setup_logger() -> logging.Logger:
    """Configures and returns the application logger."""
    logger = logging.getLogger(Settings.SYSTEM_NAME)
    
    # If logger is already configured, don't add duplicate handlers
    if logger.handlers:
        return logger
        
    logger.setLevel(getattr(logging, Settings.LOG_LEVEL.upper(), logging.INFO))
    
    # Create file handler
    file_handler = logging.FileHandler(Settings.LOG_FILE, encoding="utf-8")
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
