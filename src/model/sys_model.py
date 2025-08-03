from pathlib import Path
import joblib
from typing import List, Optional
import numpy as np
from .utils import calculate_ndvi, calculate_ndwi, log_execution_time
import logging

class GrowthStageModel:
    """Wrapper class for the growth stage prediction model."""
    
    def __init__(self, model_path: Path):
        self.logger = logging.getLogger(__name__)
        self.model = self._load_model(model_path)
        self.logger.info("GrowthStageModel initialized successfully")
    
    def _load_model(self, model_path: Path):
        """Load the trained model."""
        try:
            model = joblib.load(model_path)
            self.logger.info(f"Model loaded successfully from {model_path}")
            return model
        except Exception as e:
            self.logger.error(f"Failed to load model from {model_path}: {e}")
            raise
    
    @log_execution_time(logging.getLogger(__name__))
    def predict_growth_stage(self, features: List[float]) -> int:
        """Predict growth stage from extracted features."""
        try:
            prediction = int(self.model.predict([features])[0])
            self.logger.debug(f"Predicted growth stage: {prediction}")
            return prediction
        except Exception as e:
            self.logger.error(f"Prediction failed: {e}")
            raise
    
    @log_execution_time(logging.getLogger(__name__))
    def extract_features(self, patch_array: np.ndarray, band_mapping: dict) -> np.ndarray:
        """Extract features from a multispectral patch array."""
        try:
            red_band = patch_array[band_mapping["RED"]]
            nir_band = patch_array[band_mapping["NIR"]]
            swir_band = patch_array[band_mapping.get("SWIR", 1)]  # Default to band 1
            
            ndvi = calculate_ndvi(nir_band, red_band)
            ndwi = calculate_ndwi(nir_band, swir_band)
            
            features = [
                np.mean(ndvi), np.std(ndvi),
                np.mean(ndwi), np.std(ndwi),
                np.percentile(nir_band, 75),
                np.mean(swir_band > np.quantile(swir_band, 0.75))
            ]
            
            self.logger.debug(f"Extracted features: {features}")
            return np.array(features)
        except KeyError as e:
            self.logger.error(f"Missing required band in patch: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Feature extraction failed: {e}")
            raise