import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import joblib
import numpy as np
import logging
from logging.handlers import RotatingFileHandler
import sys
import datetime

def setup_logging(log_dir: Path = Path("logs"), 
                 log_file: str = "app.log",
                 max_bytes: int = 10*1024*1024,  # 10MB
                 backup_count: int = 5) -> logging.Logger:
    """
    Set up logging configuration with both file and console output.
    
    Args:
        log_dir: Directory to store log files
        log_file: Name of the log file
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup logs to keep
        
    Returns:
        Configured logger instance
    """
    log_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    log_path = log_dir / log_file
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_path, 
        maxBytes=max_bytes, 
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def log_execution_time(logger: logging.Logger):
    """
    Decorator to log the execution time of a function.
    
    Args:
        logger: Configured logger instance
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = datetime.datetime.now()
            logger.info(f"Starting {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                end_time = datetime.datetime.now()
                duration = end_time - start_time
                logger.info(
                    f"Completed {func.__name__} in {duration.total_seconds():.2f} seconds"
                )
                return result
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
                raise
        
        return wrapper
    return decorator

def load_config(config_path: Path = Path("./config/config.yml")) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    logger = logging.getLogger(__name__)
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuration loaded successfully from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        raise

def load_model() -> Any:
    """Load a trained ML model using YAML."""
    logger = logging.getLogger(__name__)
    try:
        default_model_dir = Path(__file__).parent / "model" / "model.joblib"
        config = load_config()
        if "model" not in config:
            logger.warning('Key "model" not found in config, using default "model.joblib".')
        model_path = Path(config.get("model", default_model_dir))
        model = joblib.load(model_path)
        logger.info(f"Model loaded successfully from {model_path}")
        return model
    except Exception as e:
        logger.error(f"Failed to load model from {model_path}: {e}")
        raise

def calculate_ndvi(nir_band: np.ndarray, red_band: np.ndarray) -> np.ndarray:
    """Calculate Normalized Difference Vegetation Index (NDVI)."""
    return (nir_band - red_band) / (nir_band + red_band + 1e-10)

def calculate_ndwi(nir_band: np.ndarray, green: np.ndarray) -> np.ndarray:
    """Calculate Normalized Difference Water Index (NDWI)."""
    return (nir_band - green) / (nir_band + green + 1e-10)