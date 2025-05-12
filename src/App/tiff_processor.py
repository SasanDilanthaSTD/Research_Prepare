import rasterio
import numpy as np

def generate_ndvi(red_path, nir_path, output_path):
    """Calculate NDVI and save as GeoTIFF."""
    with rasterio.open(red_path) as red_src:
        red = red_src.read(1).astype(float)
        profile = red_src.profile
    
    with rasterio.open(nir_path) as nir_src:
        nir = nir_src.read(1).astype(float)
    
    ndvi = (nir - red) / (nir + red + 1e-10)  # Avoid division by zero
    profile.update(dtype=rasterio.float32, count=1)
    
    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(ndvi, 1)