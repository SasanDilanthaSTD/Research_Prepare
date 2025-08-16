import sys
import os
import geopandas as gpd

# Add the project root or src folder to sys.path
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    # ensure gpd is imported
    print(f"Importing modules {gpd.__version__}")

    from utils import log_execution_time   # from src/utils.py
    from config import Config       # from src/config/config.py
    
    from component import TiffProcessor
    from component import MapGenerator

    print("Modules imported successfully")
except ImportError as e:
    print(f"Error importing modules: {e}")

# def hello():
#     return "Hello, local package!"