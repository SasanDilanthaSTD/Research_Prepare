import rasterio
import numpy as np
import os
import joblib # For loading your trained ML model
from pathlib import Path
from shapely.geometry import Polygon, mapping
import json
import geopandas as gpd
import matplotlib.pyplot as plt
import contextily as cx # For adding basemaps

# Get the directory of the current script file
script_dir = Path(__file__).parent  # E:\Research\Research_Prepare\src\Sample
src_dir = script_dir.parent  # E:\Research\Research_Prepare\src
root_dir = src_dir.parent  # E:\Research\Research_Prepare

# --- Configuration ---
# Path to your multispectral UAV image
#UAV_IMAGE_PATH = Path("../../temp/odm_orthophoto/odm_orthophoto.tif")
UAV_IMAGE_PATH = root_dir / "temp" / "odm_orthophoto" / "odm_orthophoto.tif"
# Path to your trained ML model
ML_MODEL_PATH = src_dir / "model" / "xgb_model_v3.joblib" 

PATCH_SIZE = 64 # Pixels for square patches
# Threshold for filtering "informationless" patches:
# Sum of all pixel values across all bands in a patch.
# Adjust this value based on your data. A very low sum indicates black/empty areas.
MIN_PIXEL_SUM_THRESHOLD = 5000 # Example: Tune this value!

# Define your growth stages in the order your model predicts them (0, 1, 2, ...)
GROWTH_STAGES = ["germination", "tillering", "grand_growth", "ripening"]

# Output GeoJSON file for map visualization
OUTPUT_GEOJSON_PATH = "sugarcane_growth_patches.geojson"

# Output image for the desktop map visualization
OUTPUT_MAP_IMAGE_PATH = "sugarcane_field_growth_map.png"

# --- Band Mapping (VERY IMPORTANT: Verify for your drone's output) ---
# Assuming DJI Phantom 4 Multispectral typical band order (0-indexed)
# If your GeoTIFF has a different order, adjust these indices.
# Example: If your drone outputs B, G, R, RE, NIR in that order.
# BAND_MAPPING = {
#     "BLUE": 0,
#     "GREEN": 1,
#     "RED": 2,
#     "RED_EDGE": 3,
#     "NIR": 4,
#     # NOTE: DJI P4M does not have a native SWIR band.
#     # If your model relies on SWIR, you need to use a different drone/sensor
#     # or find an alternative feature.
#     # If bands[4] in your original data was intended as SWIR, it's very unusual for P4M.
#     # For now, I'll use NIR as a placeholder for the SWIR index if needed,
#     # but be warned that NDWI will be based on NIR-NIR, which is zero.
#     # You likely need to re-evaluate your features if P4M is your only data source.
#     "SWIR_PLACEHOLDER": 4 # Using NIR band as placeholder for index 4 if SWIR is not present
#                           # This will make NDWI calculation problematic.
#                           # Adjust if your TIFF truly has a SWIR band at a specific index.
# }

BAND_MAPPING = {
    "RED": 0,
    "NIR": 1,
    "SWIR": 2
}

# --- Utility Functions ---

def calculate_ndvi(nir_band, red_band):
    """Calculates Normalized Difference Vegetation Index (NDVI)."""
    return (nir_band - red_band) / (nir_band + red_band + 1e-10)

# def calculate_ndwi(nir_band, swir_band):
#     """
#     Calculates Normalized Difference Water Index (NDWI).
#     WARNING: For DJI P4M, this assumes a SWIR band. If 'swir_band' is actually NIR,
#     this calculation will be problematic (often near zero or NaN).
#     Consider if NDWI is relevant/possible for your sensor data.
#     """
#     # Check for zero sum to avoid division by zero
#     sum_bands = nir_band + swir_band
#     ndwi = np.zeros_like(nir_band, dtype=float)
#     non_zero_sum = sum_bands != 0
#     ndwi[non_zero_sum] = (nir_band[non_zero_sum] - swir_band[non_zero_sum]) / (sum_bands[non_zero_sum] + 1e-10)
#     return ndwi
def calculate_ndwi(nir, swir):
    return (nir - swir) / (nir + swir + 1e-10)

def extract_features_from_patch_array(patch_array):
    """
    Extracts features from a single multispectral patch NumPy array.
    Expects patch_array shape: (num_bands, height, width)
    """
    features = []
    
    # Safely get band data using BAND_MAPPING
    try:
        red_band = patch_array[BAND_MAPPING["RED"]].astype(float)
        nir_band = patch_array[BAND_MAPPING["NIR"]].astype(float)
        swir_band = patch_array[BAND_MAPPING["SWIR"]].astype(float)
        
        # Determine SWIR band: If a true SWIR band is not available,
        # NDWI calculation will be affected.
        # if "SWIR_TRUE" in BAND_MAPPING: # Use this if you have a real SWIR band defined
        #     swir_band = patch_array[BAND_MAPPING["SWIR_TRUE"]].astype(float)
        # elif "SWIR_PLACEHOLDER" in BAND_MAPPING:
        #     swir_band = patch_array[BAND_MAPPING["SWIR_PLACEHOLDER"]].astype(float)
        #     print("Warning: Using placeholder band for SWIR. NDWI may not be accurate.", flush=True)
        # else:
        #     print("Error: No SWIR band defined in BAND_MAPPING. Cannot calculate NDWI.", flush=True)
        #     # You must handle this: either return fewer features or raise an error.
        #     # For robustness, returning NaNs for NDWI features.
        #     ndvi = calculate_ndvi(nir_band, red_band)
        #     return [
        #         np.nanmean(ndvi), np.nanstd(ndvi),
        #         np.nan, np.nan, # NDWI features as NaN
        #         np.percentile(nir_band, 75),
        #         np.nan # SWIR quantile feature as NaN
        #     ]


        ndvi = calculate_ndvi(nir_band, red_band)
        ndwi = calculate_ndwi(nir_band, swir_band) # This line will use the placeholder/actual SWIR

        features = [
            np.nanmean(ndvi), np.nanstd(ndvi), # nanmean/nanstd to handle potential NaNs from VIs
            np.nanmean(ndwi), np.nanstd(ndwi),
            np.percentile(nir_band, 75),
            # np.mean(swir_band > np.quantile(swir_band, 0.75)) # This feature seems specific, ensure it works.
            # Simplified for robustness if quantile on uniform arrays is an issue
            np.mean(swir_band[swir_band > np.percentile(swir_band, 75)]) if swir_band.size > 0 else 0.0
        ]
        
        # Check for NaN/Inf in features
        # if any(np.isnan(f) or np.isinf(f) for f in features):
        #     print(f"Warning: Extracted features contain NaN/Inf: {features}", flush=True)
        #     # Return a list of NaNs if any feature is invalid, this patch will likely be skipped by ML model.
        #     return [np.nan] * len(features)
        
        return features

    except IndexError as e:
        print(f"Error accessing band in patch: {e}. Check BAND_MAPPING and GeoTIFF band count.", flush=True)
        return [np.nan] * 6 # Return NaNs if band access fails
    except Exception as e:
        print(f"An unexpected error occurred during feature extraction: {e}", flush=True)
        return [np.nan] * 6 # Generic error


# --- Main Processing Logic ---

def process_field_for_mapping(image_path: Path, ml_model, growth_stages: list,
                              patch_size: int = 64, min_pixel_sum_threshold: int = 1000) -> Path:
    """
    Processes a multispectral GeoTIFF, extracts valid patches,
    predicts growth stages in batch, and generates a GeoJSON file.

    Args:
        image_path (Path): Path to the input multispectral GeoTIFF.
        ml_model: Loaded scikit-learn compatible ML model.
        growth_stages (list): List of growth stage names corresponding to model's labels.
        patch_size (int): Size of the square patches (e.g., 64).
        min_pixel_sum_threshold (int): Patches with a total pixel sum below this
                                       threshold will be considered "informationless" (black)
                                       and skipped. Tune this value.

    Returns:
        Path: Path to the generated GeoJSON file.
    """
    print(f"Starting processing for: {image_path.name}", flush=True)
    
    patches_to_process = [] # Stores (patch_data, r_start, c_start)
    
    with rasterio.open(image_path) as src:
        # Read all image data once for memory efficiency in patch extraction
        # This assumes the image fits in memory. For extremely large images,
        # you'd need to process by window.
        image_data = src.read() 
        profile = src.profile
        transform = src.transform
        nodata_val = src.nodata 

        bands, h, w = image_data.shape
        print(f"Image dimensions: {h}x{w} pixels, {bands} bands.", flush=True)
        
        num_patches_skipped = 0
        total_possible_patches = 0

        for r_start in range(0, h, patch_size):
            for c_start in range(0, w, patch_size):
                total_possible_patches += 1
                r_end = r_start + patch_size
                c_end = c_start + patch_size

                # Ensure patch fits exactly within image bounds
                if r_end > h or c_end > w:
                    # Skip partial patches at the edges for simplicity.
                    # Alternatively, you could pad them to PATCH_SIZE if your model handles it.
                    num_patches_skipped += 1
                    continue

                patch_data = image_data[:, r_start:r_end, c_start:c_end]

                # --- Filtering for "informationless" patches ---
                # 1. Check for nodata values (if defined in GeoTIFF)
                # if nodata_val is not None and np.all(patch_data == nodata_val):
                #     num_patches_skipped += 1
                #     continue
                
                # # 2. Check if the patch is mostly black/very low intensity
                # if np.sum(patch_data) < min_pixel_sum_threshold:
                #     num_patches_skipped += 1
                #     continue
                
                # # 3. Basic check for sufficient band data for feature extraction
                # if patch_data.shape[0] < max(BAND_MAPPING.values()) + 1:
                #     print(f"Skipping patch at {r_start},{c_start}: Not enough bands ({patch_data.shape[0]}) for required indexing.", flush=True)
                #     num_patches_skipped += 1
                #     continue

                patches_to_process.append((patch_data, r_start, c_start))

    print(f"Found {len(patches_to_process)} valid patches to process out of {total_possible_patches} possible patches.", flush=True)
    print(f"Skipped {num_patches_skipped} informationless/partial patches.", flush=True)

    if not patches_to_process:
        print("No valid patches found to process. Exiting.", flush=True)
        return None

    # --- Batch Feature Extraction ---
    print("Extracting features in batch...", flush=True)
    # Extract features for all valid patches
    # Use list comprehension for efficient feature extraction
    all_features = [extract_features_from_patch_array(p[0]) for p in patches_to_process]
    
    # Filter out patches where feature extraction failed (returned NaNs)
    valid_features_and_indices = []
    for i, features in enumerate(all_features):
        # if not any(np.isnan(f) for f in features): # Check if any feature is NaN
        #     valid_features_and_indices.append((features, i))
        # else:
        #     print(f"Skipping patch {i} due to invalid features (NaN/Inf).", flush=True)
        valid_features_and_indices.append((features, i))

    if not valid_features_and_indices:
        print("No valid features extracted after filtering. Exiting.", flush=True)
        return None

    # Separate features and original indices
    features_for_prediction = np.array([item[0] for item in valid_features_and_indices])
    original_patch_indices = [item[1] for item in valid_features_and_indices]
    
    print(f"Successfully extracted features for {len(features_for_prediction)} patches.", flush=True)

    # --- Batch Prediction ---
    print("Performing batch prediction...", flush=True)
    predictions_labels = ml_model.predict(features_for_prediction)
    predictions_stages = [growth_stages[label] for label in predictions_labels]
    
    print("Prediction complete. Generating GeoJSON.", flush=True)

    # --- GeoJSON Generation ---
    geojson_features = []
    with rasterio.open(image_path) as src: # Re-open for transform, minimal memory impact
        transform = src.transform

        for i, predicted_stage in zip(original_patch_indices, predictions_stages):
            _patch_data, r_start, c_start = patches_to_process[i] # Get original r_start, c_start

            # Calculate geographic coordinates for GeoJSON
            ul_lon, ul_lat = transform * (c_start, r_start)
            ur_lon, ur_lat = transform * (c_start + patch_size, r_start)
            lr_lon, lr_lat = transform * (c_start + patch_size, r_start + patch_size)
            ll_lon, ll_lat = transform * (c_start, r_start + patch_size)

            patch_polygon = Polygon([
                (ul_lon, ul_lat),
                (ur_lon, ur_lat),
                (lr_lon, lr_lat),
                (ll_lon, ll_lat),
                (ul_lon, ul_lat) # Close the polygon
            ])

            geojson_features.append({
                "type": "Feature",
                "geometry": mapping(patch_polygon),
                "properties": {
                    "growth_stage": predicted_stage,
                    "row_start": r_start,
                    "col_start": c_start
                }
            })
    
    output_geojson_data = {
        "type": "FeatureCollection",
        "features": geojson_features
    }

    with open(OUTPUT_GEOJSON_PATH, "w") as f:
        json.dump(output_geojson_data, f, indent=2)

    print(f"GeoJSON data saved to {OUTPUT_GEOJSON_PATH}", flush=True)
    return Path(OUTPUT_GEOJSON_PATH)


# --- Map Visualization Logic ---

def display_growth_stage_map(geojson_path: Path, output_map_path: Path, growth_stages: list):
    """
    Loads GeoJSON data and displays it on a map using geopandas and matplotlib.
    Saves the map as an image.
    """
    print(f"Loading GeoJSON for mapping: {geojson_path.name}", flush=True)
    try:
        gdf = gpd.read_file(geojson_path)
    except Exception as e:
        print(f"Error loading GeoJSON: {e}. Ensure the file is valid.", flush=True)
        return

    if gdf.empty:
        print("GeoJSON file is empty. Nothing to map.", flush=True)
        return

    print(f"Successfully loaded {len(gdf)} features for mapping.", flush=True)

    # Define a color map for your growth stages
    # Assign distinct colors to each stage
    stage_colors_map = {
        "germination": "#a1d99b", # Light Green
        "tillering": "#74c476",   # Medium Green
        "grand_growth": "#31a354", # Dark Green
        "ripening": "#fd8d3c",    # Orange
        # Add more if you have other stages and ensure they match GROWTH_STAGES
    }

    # Prepare for plotting
    fig, ax = plt.subplots(1, 1, figsize=(15, 15)) # Adjust figure size as needed

    # Reproject GeoDataFrame to Web Mercator (EPSG:3857) for `contextily` basemaps
    # Check if CRS is already 3857 or 4326 (WGS84). If 4326, reproject.
    if gdf.crs is None:
        print("Warning: GeoDataFrame has no CRS. Assuming WGS84 (EPSG:4326).", flush=True)
        gdf = gdf.set_crs(epsg=4326) # Set to common GPS CRS
    
    gdf_proj = gdf.to_crs(epsg=3857) # Reproject for basemap
    # if gdf.crs is None:
    #     print("Warning: GeoDataFrame has no CRS. Assuming input GeoTIFF's CRS (e.g., EPSG:5234).", flush=True)
    #     # You might want to explicitly set the CRS if you are SURE it's EPSG:5234
    #     gdf = gdf.set_crs(epsg=5234) 
    
    # gdf_proj = gdf.to_crs(epsg=3857) # Reproject for basemap compatibility

    # Plot the patches, colored by 'growth_stage'
    # Use categorical plotting for a proper legend
    gdf_proj.plot(column='growth_stage',
                  cmap=plt.colormaps['viridis'], # A generic colormap, can be customized
                  categorical=True, # Important for proper legend and color assignment
                  legend=True,
                  legend_kwds={'title': 'Growth Stage', 'loc': 'lower left'},
                  edgecolor='black',
                  linewidth=0.5,
                  ax=ax,
                  missing_kwds={
                    "color": "lightgrey",
                    "edgecolor": "red",
                    "hatch": "///",
                    "label": "Missing values",
                  }
                 )
    
    # Custom color assignment for exact stage_colors_map control:
    # Get unique stages present in the data for robust colormapping
    unique_stages_in_data = gdf_proj['growth_stage'].unique()
    colors = [stage_colors_map.get(stage, 'gray') for stage in unique_stages_in_data]
    
    # Create a custom legend manually if needed, or rely on automatic categorical plot legend.
    # The automatic one (above) is usually good, but if you need exact colors matching
    # your `stage_colors_map`, you'd do:
    from matplotlib.colors import ListedColormap
    # Create a colormap for the stages found in data
    cmap_custom = ListedColormap([stage_colors_map.get(s, 'gray') for s in sorted(unique_stages_in_data)])
    
    gdf_proj.plot(column='growth_stage',
                  cmap=cmap_custom,
                  categorical=True,
                  legend=True,
                  legend_kwds={'title': 'Growth Stage', 'loc': 'lower left', 'bbox_to_anchor': (1, 0.5)}, # Example adjust legend position
                  edgecolor='black',
                  linewidth=0.5,
                  ax=ax
                 )


    # Add a basemap for context
    try:
        # cx.add_basemap(ax, crs=gdf_proj.crs.to_string(), source=cx.providers.Esri.WorldImagery) # Satellite imagery
        cx.add_basemap(ax, crs=gdf_proj.crs.to_string(), source=cx.providers.OpenStreetMap.Mapnik) # Satellite imagery
        
        # cx.add_basemap(ax, crs=gdf_proj.crs.to_string(), source=cx.providers.OpenStreetMap.Mapnik) # OpenStreetMap
    except Exception as e:
        print(f"Could not add basemap: {e}. Check internet connection or Contextily providers.", flush=True)

    ax.set_title(f'Sugarcane Field Growth Stages - {UAV_IMAGE_PATH.name}')
    ax.set_axis_off() # Hide axes for a cleaner map look

    plt.tight_layout() # Adjust layout to prevent labels/legend overlapping
    
    # Save the map to an image file
    plt.savefig(output_map_path, dpi=300, bbox_inches='tight')
    print(f"Map saved to {output_map_path}", flush=True)

    # Display the plot (optional, will open a window)
    plt.show()

# --- Main Execution Block ---
if __name__ == "__main__":
    # --- 1. Load your ML Model ---
    try:
        # Load your actual trained model here
        # ml_model = joblib.load(ML_MODEL_PATH)
        print(f"Attempting to load ML model from {ML_MODEL_PATH}...", flush=True)
        if not os.path.exists(ML_MODEL_PATH):
            raise FileNotFoundError(f"Model file not found at {ML_MODEL_PATH}.")
        ml_model = joblib.load(ML_MODEL_PATH)
        print("ML model loaded successfully.", flush=True)
    except Exception as e:
        print(f"Error loading ML model: {e}. Please ensure it's a valid joblib/pickle file.", flush=True)
        exit() # Exit if model cannot be loaded

    # --- 2. Process Field Data and Get Predictions ---
    if not UAV_IMAGE_PATH.exists():
        print(f"Error: UAV image not found at {UAV_IMAGE_PATH}.", flush=True)
        print("Please update UAV_IMAGE_PATH to the correct location of your .tif file.", flush=True)
    else:
        generated_geojson_path = process_field_for_mapping(
            UAV_IMAGE_PATH,
            ml_model,
            GROWTH_STAGES,
            patch_size=PATCH_SIZE,
            min_pixel_sum_threshold=MIN_PIXEL_SUM_THRESHOLD
        )

        # --- 3. Display Map ---
        if generated_geojson_path and generated_geojson_path.exists():
            display_growth_stage_map(generated_geojson_path, OUTPUT_MAP_IMAGE_PATH, GROWTH_STAGES)
        else:
            print("GeoJSON file was not generated or not found. Cannot display map.", flush=True)