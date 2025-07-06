import rasterio
import numpy as np
import os
import matplotlib.pyplot as plt
from pathlib import Path


# ------------------------- image devide related -------------------------

def load_geotiff(image_path):
    """Load a multispectral GeoTIFF image using rasterio."""
    with rasterio.open(image_path) as src:
        image = src.read()
        profile = src.profile
    return image, profile