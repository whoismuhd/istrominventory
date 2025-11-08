"""
Logging module for Istrom Inventory Management System
Replaces print() statements with proper logging
"""
import logging
import sys
from pathlib import Path

# Create logs directory if it doesn't exist
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'istrominventory.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Create logger instance
logger = logging.getLogger('istrominventory')

def log_info(message):
    """Log info message"""
    logger.info(message)

def log_error(message, exc_info=False):
    """Log error message"""
    logger.error(message, exc_info=exc_info)

def log_warning(message):
    """Log warning message"""
    logger.warning(message)

def log_debug(message):
    """Log debug message"""
    logger.debug(message)

# For backward compatibility - can be used as drop-in replacement for print()
def log(message, level='info'):
    """Log message with specified level"""
    if level == 'error':
        log_error(message)
    elif level == 'warning':
        log_warning(message)
    elif level == 'debug':
        log_debug(message)
    else:
        log_info(message)


