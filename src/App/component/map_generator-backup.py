from pathlib import Path
from typing import Dict, Optional
import geopandas as gpd
from folium import Map, GeoJson, GeoJsonTooltip
import logging

from src.App.utils import log_execution_time
from src.App.config import Config

class MapGenerator:
    """Generates interactive maps from GeoJSON files."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.logger.info("MapGenerator initialized successfully")
    
    @log_execution_time(logging.getLogger(__name__))
    def generate_map(
        self,
        geojson_path: Path,
        output_dir: Optional[Path] = None,
        map_name: str = "sugarcane_growth_map.html"
    ) -> Path:
        """
        Generate an interactive map from a GeoJSON file.
        """
        output_dir = output_dir or self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / map_name
        
        self.logger.info(f"Generating map from {geojson_path}")
        
        try:
            geo_data = gpd.read_file(geojson_path)
            
            if geo_data.empty:
                error_msg = "GeoJSON file is empty. Cannot create map."
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Convert to WGS84 (EPSG:4326) for Folium
            geo_data = geo_data.to_crs("EPSG:4326")
            centroid = geo_data.geometry.centroid
            map_center = [centroid.y.mean(), centroid.x.mean()]
            
            self.logger.debug(f"Map center coordinates: {map_center}")
            
            m = Map(location=map_center, zoom_start=16, tiles="OpenStreetMap")
            
            GeoJson(
                geo_data,
                style_function=self._style_function,
                tooltip=GeoJsonTooltip(fields=['growth_stage'])
            ).add_to(m)
            
            m.save(output_path)
            self.logger.info(f"Interactive map saved to {output_path}")
            return output_path
        except Exception as e:
            self.logger.error(f"Failed to generate map: {e}")
            raise
    
    def _style_function(self, feature):
        """Style function for GeoJSON features."""
        growth_stage = feature['properties'].get('growth_stage')
        color = self.config.default_colors.get(growth_stage, '#808080')
        return {
            'fillColor': color,
            'color': 'black',
            'weight': 0.2,
            'fillOpacity': 0.7
        }