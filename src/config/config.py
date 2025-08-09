# config.py
from pathlib import Path
from typing import Dict, Any, List
from .utils import load_config, setup_logging
import logging

class Config:
    """Configuration manager that reads from YAML file."""
    
    def __init__(self):
        self.src_dir = Path(__file__).parent.parent.parent / "src"
        self.config_path = self.src_dir / "config" / "config.yaml"
        self.logger = setup_logging()
        self.config = load_config(self.config_path)
        self.root_dir = Path(__file__).parent.parent.parent
        
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
        return self.root_dir / self.config.get("paths", {}).get("model", "src/model/model.joblib")
    
    @property
    def temp_dir(self) -> Path:
        return self.root_dir / self.config.get("paths", {}).get("temp", "temp")
    
    @property
    def temp_map_dir(self) -> Path:
        return self.root_dir / self.config.get("paths", {}).get("temp_map", "temp_map")

    @property
    def output_dir(self) -> Path:
        return self.root_dir / self.config.get("paths", {}).get("output", "output")

    @property
    def log_dir(self) -> Path:
        return self.root_dir / self.config.get("paths", {}).get("logs", "logs")
    
    def _validate_paths(self):
        """Validate that all required paths exist."""
        self.logger.info("Validating paths...")
        
        if not self.model_path.exists():
            error_msg = f"Model not found at {self.model_path}"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.temp_map_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("All paths validated successfully")