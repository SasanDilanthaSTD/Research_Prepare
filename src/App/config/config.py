import sys
import os
from pathlib import Path
from typing import Dict, Any, List
import logging

from src.App.utils import load_config, setup_logging

class Config:
    """Configuration manager that reads from YAML file."""
    
    def __init__(self):
        # Get the root directory (where main.py is located)
        self.root_dir = Path(__file__).parent.parent.parent.parent
        self.src_dir = Path(__file__).parent.parent.parent
        self.app = Path(__file__).parent.parent
        self.config_path = self.app / "config" / "config.yml"
        self.logger = setup_logging()
        self.config = load_config(self.config_path)
        
        # Validate and set paths
        self._validate_paths()
        self.logger.info("Configuration initialized successfully")
        
    @property
    def band_mappings(self) -> Dict[str, Dict[str, int]]:
        return self.config.get("band_mappings", {})
    
    @property
    def default_colors(self) -> Dict[str, str]:
        colors = self.config.get("default_colors", {})
        return {
            "germination": colors.get("germination", "#B3E5FC"),
            "tillering": colors.get("tillering", "#8BC34A"),
            "grand_growth": colors.get("grand_growth", "#4CAF50"),
            "ripening": colors.get("ripening", "#FFEB3B"),
            None: colors.get("unclassified", "#808080")
        }
    
    @property
    def growth_stages(self) -> List[str]:
        return ["germination", "tillering", "grand_growth", "ripening"]
    
    @property
    def patch_size(self) -> int:
        return self.config.get("processing", {}).get("patch_size", 64)
    
    @property
    def min_pixel_sum_threshold(self) -> int:
        return self.config.get("processing", {}).get("min_pixel_sum_threshold", 5000)
    
    @property
    def band_mapping_type(self) -> str:
        return self.config.get("processing", {}).get("band_mapping_type", "ODM")
    
    @property
    def model_path(self) -> Path:
        return self.app / "model" / "XGB_model_v13.joblib"
    
    @property
    def temp_dir(self) -> Path:
        # Points to root/temp
        return self.root_dir / "temp"
    
    @property
    def temp_map_dir(self) -> Path:
        # Points to root/src/temp_map
        return self.src_dir / "temp_map"

    @property
    def output_dir(self) -> Path:
        return self.src_dir / "temp_map"

    @property
    def log_dir(self) -> Path:
        return self.root_dir / "logs"
    
    @property
    def resource_dir(self) -> Path:
        return self.app / "resource"
    
    @property
    def otho_photo_backup_dir(self) -> Path:
        return self.app / "img_backup"
    
    def _validate_paths(self):
        """Validate that all required paths exist."""
        self.logger.info("Validating paths...")
        
        if not self.model_path.exists():
            error_msg = f"Model not found at {self.model_path}"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # Create necessary directories
        self.temp_map_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.resource_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("All paths validated successfully")