import os
import numpy as np
import rasterio
import joblib 
from pathlib import Path
import matplotlib.pyplot as plt

# load the model
def load_model():
    """Load a pre-trained XGBoost model from a file."""
    model_path = Path(__file__).parent / "xgb_model_v3.joblib"
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    model = joblib.load(model_path)
    return model

if __name__ == "__main__":
    try:
        model = load_model()
        print("Model loaded successfully!")
        # Optionally, print model details or type
        print(f"Model type: {type(model)}")
    except FileNotFoundError as e:
        print(e)
    except Exception as e:
        print(f"An error occurred while loading the model: {e}")