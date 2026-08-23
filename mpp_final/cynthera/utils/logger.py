"""
Logging infrastructure for the Cynthera drug repurposing system.
"""
import logging
import os
from pathlib import Path
from typing import Optional
import yaml


def setup_logger(
    name: str,
    config_path: Optional[str] = None,
    level: Optional[str] = None
) -> logging.Logger:
    """
    Set up a logger with file and console handlers.
    
    Args:
        name: Logger name (usually __name__)
        config_path: Path to config.yaml (optional)
        level: Override log level (optional)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Load config if provided
    log_level = "INFO"
    log_file = "logs/cynthera.log"
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            log_level = config.get('logging', {}).get('level', 'INFO')
            log_file = config.get('logging', {}).get('file', 'logs/cynthera.log')
            log_format = config.get('logging', {}).get('format', log_format)
    
    # Override with explicit level if provided
    if level:
        log_level = level
    
    # Set level
    logger.setLevel(getattr(logging, log_level))
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(getattr(logging, log_level))
    file_formatter = logging.Formatter(log_format)
    file_handler.setFormatter(file_formatter)
    
    # Console handler (force UTF-8 to avoid Windows cp1252 crashes with Unicode)
    import sys
    console_handler = logging.StreamHandler(
        stream=open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False)
    )
    console_handler.setLevel(getattr(logging, log_level))
    console_formatter = logging.Formatter(log_format)
    console_handler.setFormatter(console_formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with default configuration.
    
    Args:
        name: Logger name
    
    Returns:
        Logger instance
    """
    config_path = "config/config.yaml"
    if os.path.exists(config_path):
        return setup_logger(name, config_path)
    else:
        return setup_logger(name)
