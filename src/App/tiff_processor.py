import rasterio
from rasterio.features import shapes
import numpy as np
import json
from pathlib import Path
import geopandas as gpd
from typing import List, Optional
import logging
from .utils import log_execution_time

from .config import Config
from .sys_model import GrowthStageModel

class TiffProcessor:
    """Processes GeoTIFF files to generate growth stage maps."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.model = GrowthStageModel(config.model_path)
        self.band_mapping = config.band_mappings[config.band_mapping_type]
        self.logger.info("TiffProcessor initialized successfully")
    
    @log_execution_time(logging.getLogger(__name__))
    def process_field(
        self,
        image_path: Path,
        output_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Process the field image and generate a GeoJSON with growth stage classifications.
        """
        output_dir = output_dir or self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_geojson_path = output_dir / "classified_output.geojson"
        
        self.logger.info(f"Starting processing for: {image_path.name}")
        
        with rasterio.open(image_path) as src:
            image_data = src.read()
            transform = src.transform
            nodata_val = src.nodata
            
            bands, h, w = image_data.shape
            self.logger.info(f"Image dimensions: {h}x{w} pixels, {bands} bands")
            
            classified_raster = np.full((h, w), fill_value=-1, dtype=np.int16)
            num_patches_skipped = 0
            total_patches = 0
            
            self.logger.info("Starting patch processing...")
            
            for r_start in range(0, h, self.config.patch_size):
                for c_start in range(0, w, self.config.patch_size):
                    total_patches += 1
                    r_end = r_start + self.config.patch_size
                    c_end = c_start + self.config.patch_size
                    
                    current_h = min(self.config.patch_size, h - r_start)
                    current_w = min(self.config.patch_size, w - c_start)
                    
                    if current_h < self.config.patch_size or current_w < self.config.patch_size:
                        num_patches_skipped += 1
                        continue
                    
                    patch_data = image_data[:, r_start:r_end, c_start:c_end]
                    
                    if nodata_val is not None and np.all(patch_data == nodata_val):
                        num_patches_skipped += 1
                        continue
                    
                    if np.sum(patch_data) < self.config.min_pixel_sum_threshold:
                        num_patches_skipped += 1
                        continue
                    
                    try:
                        features = self.model.extract_features(patch_data, self.band_mapping)
                        if any(np.isnan(f) for f in features):
                            num_patches_skipped += 1
                            continue
                            
                        prediction_label = self.model.predict_growth_stage(features)
                        classified_raster[r_start:r_end, c_start:c_end] = prediction_label
                    except Exception as e:
                        self.logger.warning(f"Skipping patch at ({r_start},{c_start}): {e}")
                        num_patches_skipped += 1
                        continue
            
            self.logger.info(
                f"Patch processing completed. Processed {total_patches - num_patches_skipped} patches, "
                f"skipped {num_patches_skipped} patches."
            )
            
            self.logger.info("Vectorizing classified raster...")
            geojson_features = []
            for geom, value in shapes(
                classified_raster.astype(np.int16),
                mask=(classified_raster != -1),
                transform=transform
            ):
                if value != -1:
                    growth_stage_name = self.config.growth_stages[int(value)]
                    geojson_features.append({
                        "type": "Feature",
                        "geometry": geom,
                        "properties": {"growth_stage": growth_stage_name}
                    })
            
            if not geojson_features:
                self.logger.warning("No features were vectorized from the raster")
                return None
            
            output_geojson_data = {
                "type": "FeatureCollection",
                "crs": {
                    "type": "name",
                    "properties": {"name": f"EPSG:{src.crs.to_epsg()}"}
                },
                "features": geojson_features
            }
            
            with open(output_geojson_path, "w") as f:
                json.dump(output_geojson_data, f, indent=2)
                
            self.logger.info(f"GeoJSON data saved to {output_geojson_path}")
            return output_geojson_path