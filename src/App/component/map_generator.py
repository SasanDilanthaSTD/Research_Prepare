from pathlib import Path
from typing import Dict, Optional
import geopandas as gpd
from folium import Map, GeoJson, GeoJsonTooltip
import logging
import shutil
from datetime import datetime

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
        output_dir = output_dir or self.config.temp_map_dir
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
            
            # Delete the classified_output.geojson file after map generation
            self._cleanup_geojson(geojson_path)
            
            # Move and cleanup orthophoto files
            self._manage_orthophoto_files()
            
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
    
    def _cleanup_geojson(self, geojson_path: Path):
        """Delete the classified_output.geojson file after map generation."""
        try:
            if geojson_path.exists():
                geojson_path.unlink()
                self.logger.info(f"Deleted GeoJSON file: {geojson_path}")
            else:
                self.logger.warning(f"GeoJSON file not found: {geojson_path}")
        except Exception as e:
            self.logger.error(f"Error deleting GeoJSON file {geojson_path}: {e}")
    
    def _manage_orthophoto_files(self):
        """Move orthophoto file to resource folder and cleanup temp directory."""
        try:
            self.logger.info("=== Starting orthophoto file management ===")
            
            # Log current directory structure for debugging
            self._log_directory_structure()
            
            # Find the orthophoto file
            orthophoto_path = self._find_orthophoto_file()
            
            if not orthophoto_path:
                self.logger.error("No orthophoto file found to move")
                return
            
            self.logger.info(f"Found orthophoto file: {orthophoto_path}")
            
            # Create timestamped folder in orthophoto backup directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            resource_folder = self.config.otho_photo_backup_dir / f"orthophoto_{timestamp}"
            resource_folder.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(f"Created resource folder: {resource_folder}")
            
            # New path for the orthophoto file
            new_orthophoto_path = resource_folder / orthophoto_path.name
            
            # Move the file
            self.logger.info(f"Moving {orthophoto_path} to {new_orthophoto_path}")
            shutil.move(str(orthophoto_path), str(new_orthophoto_path))
            self.logger.info(f"Successfully moved orthophoto file")
            
            # Cleanup temp directory
            self._cleanup_temp_directory()
            
            self.logger.info("=== Orthophoto file management completed ===")
            
        except Exception as e:
            self.logger.error(f"Error managing orthophoto files: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
    
    def _log_directory_structure(self):
        """Log the directory structure for debugging."""
        try:
            self.logger.info("=== Current Directory Structure ===")
            self.logger.info(f"Root directory: {self.config.root_dir}")
            self.logger.info(f"Root directory exists: {self.config.root_dir.exists()}")
            
            if self.config.root_dir.exists():
                for item in self.config.root_dir.iterdir():
                    if item.is_dir():
                        self.logger.info(f"Directory: {item.name}")
                        # List contents of important directories
                        if item.name == "temp":
                            for subitem in item.iterdir():
                                self.logger.info(f"  - {subitem.name}")
                    else:
                        self.logger.info(f"File: {item.name}")
            
            self.logger.info(f"Temp directory: {self.config.temp_dir}")
            self.logger.info(f"Temp directory exists: {self.config.temp_dir.exists()}")
            
            if self.config.temp_dir.exists():
                self.logger.info("Contents of temp directory:")
                for item in self.config.temp_dir.rglob("*"):
                    relative_path = item.relative_to(self.config.temp_dir)
                    self.logger.info(f"  - {relative_path}")
            
            self.logger.info("=== End Directory Structure ===")
        except Exception as e:
            self.logger.error(f"Error logging directory structure: {e}")
    
    def _find_orthophoto_file(self) -> Optional[Path]:
        """Find the orthophoto file recursively in the temp directory."""
        try:
            if not self.config.temp_dir.exists():
                self.logger.error(f"Temp directory does not exist: {self.config.temp_dir}")
                return None
            
            # Look for .tif files recursively in temp directory
            tif_files = list(self.config.temp_dir.rglob("*.tif"))
            
            self.logger.info(f"Found {len(tif_files)} TIF files in temp directory")
            
            if not tif_files:
                # Also look for .TIFF files
                tiff_files = list(self.config.temp_dir.rglob("*.tiff"))
                tif_files.extend(tiff_files)
                self.logger.info(f"Found {len(tiff_files)} TIFF files in temp directory")
            
            if not tif_files:
                self.logger.error("No TIF or TIFF files found in temp directory")
                return None
            
            # Log all found files
            for tif_file in tif_files:
                self.logger.info(f"Found TIF file: {tif_file}")
            
            # Prefer files named 'odm_orthophoto.tif'
            for tif_file in tif_files:
                if tif_file.name.lower() == "odm_orthophoto.tif":
                    self.logger.info(f"Selected orthophoto file: {tif_file}")
                    return tif_file
            
            # If not found, return the largest TIF file (likely the orthophoto)
            if tif_files:
                largest_file = max(tif_files, key=lambda x: x.stat().st_size)
                self.logger.info(f"Selected largest TIF file: {largest_file} (size: {largest_file.stat().st_size} bytes)")
                return largest_file
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding orthophoto file: {e}")
            return None
    
    def _cleanup_temp_directory(self):
        """Delete the entire temp directory after moving the orthophoto."""
        try:
            self.logger.info(f"Attempting to cleanup temp directory: {self.config.temp_dir}")
            
            if not self.config.temp_dir.exists():
                self.logger.warning(f"Temp directory does not exist: {self.config.temp_dir}")
                return
            
            # Check directory contents before deletion
            contents = list(self.config.temp_dir.rglob("*"))
            self.logger.info(f"Temp directory contains {len(contents)} items")
            
            for item in contents:
                self.logger.info(f"  - {item.relative_to(self.config.temp_dir)}")
            
            # Delete the directory
            shutil.rmtree(self.config.temp_dir)
            self.logger.info(f"Successfully deleted temp directory: {self.config.temp_dir}")
            
            # Verify deletion
            if not self.config.temp_dir.exists():
                self.logger.info("Temp directory deletion verified")
            else:
                self.logger.error("Temp directory still exists after deletion attempt")
                
        except Exception as e:
            self.logger.error(f"Error deleting temp directory {self.config.temp_dir}: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")