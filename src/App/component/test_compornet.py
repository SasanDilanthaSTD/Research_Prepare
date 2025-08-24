import sys
import os
from pathlib import Path

from src.App.utils import load_config

# src_dir = Path(__file__).parent.parent.parent
# config_path = src_dir / "App" / "config" / "config.yml"

main = Path(__file__).parent.parent.parent.parent
config_path = main / "config.yml"

try:
    config =  load_config(config_path)
    print(f"Config loaded successfully from {config_path}")
except Exception as e:
    print(f"Error loading config: {e}")
    config = {}
    
# print the config for verification
print("Configuration:", config)

app = Path(__file__).parent.parent
print("App directory:", app)

